package routes

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"path/filepath"
	"strings"

	"github.com/google/uuid"
	"github.com/gorilla/mux"
	"github.com/redis/go-redis/v9"

	"github.com/veloworld/backend/internal/queue"
	"github.com/veloworld/backend/internal/storage"
)

type Handler struct {
	DB      *sql.DB
	Redis   *redis.Client
	Storage *storage.S3Storage
	Queue   *queue.JobQueue
}

type Route struct {
	ID             uuid.UUID `json:"id"`
	Name           string    `json:"name"`
	Description    *string   `json:"description,omitempty"`
	DistanceM      float64   `json:"distance_m"`
	ElevationGainM *float64  `json:"elevation_gain_m,omitempty"`
	ProcessingStatus string  `json:"processing_status"`
	IsPublic       bool      `json:"is_public"`
	CreatedAt      string    `json:"created_at"`
}

type UploadRouteRequest struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
}

func NewHandler(db *sql.DB, redis *redis.Client, storage *storage.S3Storage, queue *queue.JobQueue) *Handler {
	return &Handler{
		DB:      db,
		Redis:   redis,
		Storage: storage,
		Queue:   queue,
	}
}

func (h *Handler) UploadRoute(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	// Parse multipart form
	err := r.ParseMultipartForm(32 << 20) // 32MB max
	if err != nil {
		http.Error(w, "Failed to parse form", http.StatusBadRequest)
		return
	}

	file, header, err := r.FormFile("route_file")
	if err != nil {
		http.Error(w, "Route file required", http.StatusBadRequest)
		return
	}
	defer file.Close()

	// Validate file extension
	ext := strings.ToLower(filepath.Ext(header.Filename))
	if ext != ".gpx" && ext != ".fit" && ext != ".tcx" {
		http.Error(w, "Unsupported file format. Use GPX, FIT, or TCX", http.StatusBadRequest)
		return
	}

	// Read file content
	fileContent, err := io.ReadAll(file)
	if err != nil {
		http.Error(w, "Failed to read file", http.StatusInternalServerError)
		return
	}

	// Basic validation - check file size
	if len(fileContent) < 100 {
		http.Error(w, "File too small", http.StatusBadRequest)
		return
	}

	// Get form data
	name := r.FormValue("name")
	if name == "" {
		name = strings.TrimSuffix(header.Filename, ext)
	}

	description := r.FormValue("description")

	// Create route record
	routeID := uuid.New()
	_, err = h.DB.Exec(`
		INSERT INTO routes (id, owner_id, name, description, source_format, s3_key, processing_status)
		VALUES ($1, $2, $3, $4, $5, $6, 'queued')`,
		routeID, userID, name, description, ext[1:], s3Key) // Remove the dot from extension
	if err != nil {
		// If database insert fails, delete the S3 file
		h.Storage.DeleteRouteFile(s3Key)
		http.Error(w, "Failed to create route", http.StatusInternalServerError)
		return
	}

	// Upload file to S3
	s3Key, err := h.Storage.UploadRouteFile(routeID, header.Filename, fileContent)
	if err != nil {
		// If S3 upload fails, delete the route record
		h.DB.Exec("DELETE FROM routes WHERE id = $1", routeID)
		http.Error(w, "Failed to store route file", http.StatusInternalServerError)
		return
	}

	// Queue processing job
	err = h.Queue.EnqueueRouteProcessing(r.Context(), routeID, s3Key, ext[1:])
	if err != nil {
		// If queuing fails, delete the route record and S3 file
		h.DB.Exec("DELETE FROM routes WHERE id = $1", routeID)
		h.Storage.DeleteRouteFile(s3Key)
		http.Error(w, "Failed to queue processing job", http.StatusInternalServerError)
		return
	}

	route := Route{
		ID:               routeID,
		Name:             name,
		Description:      &description,
		ProcessingStatus: "queued",
		IsPublic:         false,
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(route)
}

func (h *Handler) ListRoutes(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	rows, err := h.DB.Query(`
		SELECT id, name, description, distance_m, elevation_gain_m, processing_status, is_public, created_at
		FROM routes
		WHERE owner_id = $1
		ORDER BY created_at DESC`,
		userID)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var routes []Route
	for rows.Next() {
		var route Route
		err := rows.Scan(&route.ID, &route.Name, &route.Description, &route.DistanceM,
			&route.ElevationGainM, &route.ProcessingStatus, &route.IsPublic, &route.CreatedAt)
		if err != nil {
			http.Error(w, "Database error", http.StatusInternalServerError)
			return
		}
		routes = append(routes, route)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(routes)
}

func (h *Handler) GetRoute(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	vars := mux.Vars(r)
	routeIDStr := vars["id"]
	routeID, err := uuid.Parse(routeIDStr)
	if err != nil {
		http.Error(w, "Invalid route ID", http.StatusBadRequest)
		return
	}

	var route Route
	err = h.DB.QueryRow(`
		SELECT id, name, description, distance_m, elevation_gain_m, processing_status, is_public, created_at
		FROM routes
		WHERE id = $1 AND owner_id = $2`,
		routeID, userID).Scan(&route.ID, &route.Name, &route.Description, &route.DistanceM,
		&route.ElevationGainM, &route.ProcessingStatus, &route.IsPublic, &route.CreatedAt)

	if err == sql.ErrNoRows {
		http.Error(w, "Route not found", http.StatusNotFound)
		return
	}
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(route)
}

func (h *Handler) GetRoutePackage(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	vars := mux.Vars(r)
	routeIDStr := vars["id"]
	routeID, err := uuid.Parse(routeIDStr)
	if err != nil {
		http.Error(w, "Invalid route ID", http.StatusBadRequest)
		return
	}

	// Check if route exists and belongs to user, and is completed
	var processingStatus string
	var s3Key string
	err = h.DB.QueryRow(`
		SELECT processing_status, s3_key
		FROM routes
		WHERE id = $1 AND owner_id = $2`,
		routeID, userID).Scan(&processingStatus, &s3Key)

	if err == sql.ErrNoRows {
		http.Error(w, "Route not found", http.StatusNotFound)
		return
	}
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	if processingStatus != "completed" {
		http.Error(w, "Route processing not completed", http.StatusBadRequest)
		return
	}

	// Get the processed package from S3
	packageData, err := h.Storage.DownloadProcessedPackage(routeID)
	if err != nil {
		http.Error(w, "Failed to retrieve processed package", http.StatusInternalServerError)
		return
	}

	// Set headers for file download
	w.Header().Set("Content-Type", "application/zip")
	w.Header().Set("Content-Disposition", fmt.Sprintf("attachment; filename=\"route_%s.zip\"", routeID.String()))
	w.Header().Set("Content-Length", strconv.Itoa(len(packageData)))

	// Write the package data
	w.Write(packageData)
}

func (h *Handler) DeleteRoute(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	vars := mux.Vars(r)
	routeIDStr := vars["id"]
	routeID, err := uuid.Parse(routeIDStr)
	if err != nil {
		http.Error(w, "Invalid route ID", http.StatusBadRequest)
		return
	}

	result, err := h.DB.Exec(`
		DELETE FROM routes
		WHERE id = $1 AND owner_id = $2`,
		routeID, userID)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	if rowsAffected == 0 {
		http.Error(w, "Route not found", http.StatusNotFound)
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func (h *Handler) ListPublicRoutes(w http.ResponseWriter, r *http.Request) {
	rows, err := h.DB.Query(`
		SELECT id, name, description, distance_m, elevation_gain_m, processing_status, is_public, created_at
		FROM routes
		WHERE is_public = true AND processing_status = 'ready'
		ORDER BY created_at DESC
		LIMIT 50`)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var routes []Route
	for rows.Next() {
		var route Route
		err := rows.Scan(&route.ID, &route.Name, &route.Description, &route.DistanceM,
			&route.ElevationGainM, &route.ProcessingStatus, &route.IsPublic, &route.CreatedAt)
		if err != nil {
			http.Error(w, "Database error", http.StatusInternalServerError)
			return
		}
		routes = append(routes, route)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(routes)
}

func (h *Handler) PublishRoute(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	vars := mux.Vars(r)
	routeIDStr := vars["id"]
	routeID, err := uuid.Parse(routeIDStr)
	if err != nil {
		http.Error(w, "Invalid route ID", http.StatusBadRequest)
		return
	}

	result, err := h.DB.Exec(`
		UPDATE routes
		SET is_public = true
		WHERE id = $1 AND owner_id = $2`,
		routeID, userID)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	if rowsAffected == 0 {
		http.Error(w, "Route not found", http.StatusNotFound)
		return
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "published"})
}

func (h *Handler) GetRoutePackage(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	vars := mux.Vars(r)
	routeIDStr := vars["id"]
	routeID, err := uuid.Parse(routeIDStr)
	if err != nil {
		http.Error(w, "Invalid route ID", http.StatusBadRequest)
		return
	}

	// Check ownership and processing status
	var processingStatus string
	err = h.DB.QueryRow(`
		SELECT processing_status
		FROM routes
		WHERE id = $1 AND owner_id = $2`,
		routeID, userID).Scan(&processingStatus)

	if err == sql.ErrNoRows {
		http.Error(w, "Route not found", http.StatusNotFound)
		return
	}
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	if processingStatus != "ready" {
		http.Error(w, fmt.Sprintf("Route processing not complete: %s", processingStatus), http.StatusBadRequest)
		return
	}

	// TODO: Return streaming package definition from S3/Redis
	http.Error(w, "Package retrieval not implemented", http.StatusNotImplemented)
}