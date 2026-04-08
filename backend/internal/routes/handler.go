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

	"github.com/veloverse/backend/internal/queue"
	"github.com/veloverse/backend/internal/storage"
)

type Handler struct {
	DB      *sql.DB
	Redis   *redis.Client
	Storage *storage.S3Storage
	Queue   *queue.JobQueue
}

type Route struct {
	ID               uuid.UUID `json:"id"`
	Name             string    `json:"name"`
	Description      *string   `json:"description,omitempty"`
	DistanceM        float64   `json:"distance_m"`
	ElevationGainM   *float64  `json:"elevation_gain_m,omitempty"`
	ProcessingStatus string    `json:"processing_status"`
	IsPublic         bool      `json:"is_public"`
	CreatedAt        string    `json:"created_at"`
}

type UploadRouteRequest struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
}

type UpdateVisibilityRequest struct {
	Visibility string `json:"visibility"`
}

type RenderPoint struct {
	DistanceM  float64 `json:"distance_m"`
	ElevationM float64 `json:"elevation_m"`
	Lat        float64 `json:"lat,omitempty"`
	Lon        float64 `json:"lon,omitempty"`
}

type RouteRenderDataResponse struct {
	RouteID        uuid.UUID     `json:"route_id"`
	DistanceM      float64       `json:"distance_m"`
	ElevationGainM float64       `json:"elevation_gain_m"`
	ProfilePoints  []RenderPoint `json:"profile_points"`
}

type routeRenderCachePayload struct {
	RouteID        string        `json:"route_id"`
	DistanceM      float64       `json:"distance_m"`
	ElevationGainM float64       `json:"elevation_gain_m"`
	ProfilePoints  []RenderPoint `json:"profile_points"`
}

func normalizeSourceFormat(format string) string {
	if format == "fits" {
		return "fit"
	}
	return format
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
	if ext != ".gpx" && ext != ".fit" && ext != ".fits" && ext != ".tcx" {
		http.Error(w, "Unsupported file format. Use GPX, FIT/FITS, or TCX", http.StatusBadRequest)
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

	// Upload file to S3 first
	s3Key, err := h.Storage.UploadRouteFile(routeID, header.Filename, fileContent)
	if err != nil {
		http.Error(w, "Failed to store route file", http.StatusInternalServerError)
		return
	}

	_, err = h.DB.Exec(`
		INSERT INTO routes (id, owner_id, name, description, distance_m, elevation_gain_m, source_format, s3_key, processing_status)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'queued')`,
		routeID, userID, name, description, 0.0, nil, normalizeSourceFormat(ext[1:]), s3Key) // Remove the dot from extension
	if err != nil {
		// If database insert fails, delete the S3 file
		h.Storage.DeleteRouteFile(s3Key)
		http.Error(w, "Failed to create route", http.StatusInternalServerError)
		return
	}

	// Queue processing job
	err = h.Queue.EnqueueRouteProcessing(r.Context(), routeID, s3Key, normalizeSourceFormat(ext[1:]))
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

func (h *Handler) UpdateVisibility(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	vars := mux.Vars(r)
	routeID, err := uuid.Parse(vars["id"])
	if err != nil {
		http.Error(w, "Invalid route ID", http.StatusBadRequest)
		return
	}

	var req UpdateVisibilityRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	visibility := strings.ToLower(strings.TrimSpace(req.Visibility))
	if visibility != "public" && visibility != "private" {
		http.Error(w, "visibility must be 'public' or 'private'", http.StatusBadRequest)
		return
	}

	isPublic := visibility == "public"
	result, err := h.DB.Exec(`
		UPDATE routes
		SET is_public = $1
		WHERE id = $2 AND owner_id = $3`,
		isPublic, routeID, userID)
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

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{"route_id": routeID, "visibility": visibility, "is_public": isPublic})
}

func (h *Handler) RetryRouteProcessing(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	vars := mux.Vars(r)
	routeID, err := uuid.Parse(vars["id"])
	if err != nil {
		http.Error(w, "Invalid route ID", http.StatusBadRequest)
		return
	}

	var s3Key string
	var sourceFormat string
	var processingStatus string
	err = h.DB.QueryRow(`
		SELECT s3_key, source_format, processing_status
		FROM routes
		WHERE id = $1 AND owner_id = $2`,
		routeID, userID).Scan(&s3Key, &sourceFormat, &processingStatus)
	if err == sql.ErrNoRows {
		http.Error(w, "Route not found", http.StatusNotFound)
		return
	}
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	if processingStatus == "ready" {
		http.Error(w, "Route is already ready", http.StatusBadRequest)
		return
	}

	if s3Key == "" || sourceFormat == "" {
		http.Error(w, "Route file metadata missing", http.StatusBadRequest)
		return
	}

	_, err = h.DB.Exec(`
		UPDATE routes
		SET processing_status = 'queued'
		WHERE id = $1 AND owner_id = $2`,
		routeID, userID)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	err = h.Queue.EnqueueRouteProcessing(r.Context(), routeID, s3Key, normalizeSourceFormat(sourceFormat))
	if err != nil {
		http.Error(w, "Failed to queue processing job", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{"route_id": routeID, "status": "queued", "retried": true})
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

func (h *Handler) GetRouteRenderData(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	vars := mux.Vars(r)
	routeID, err := uuid.Parse(vars["id"])
	if err != nil {
		http.Error(w, "Invalid route ID", http.StatusBadRequest)
		return
	}

	var distanceM float64
	var elevationGain sql.NullFloat64
	var processingStatus string
	err = h.DB.QueryRow(`
		SELECT distance_m, elevation_gain_m, processing_status
		FROM routes
		WHERE id = $1 AND owner_id = $2`,
		routeID, userID).Scan(&distanceM, &elevationGain, &processingStatus)
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

	if distanceM <= 0 {
		distanceM = 10000
	}
	elevGain := 180.0
	if elevationGain.Valid && elevationGain.Float64 > 0 {
		elevGain = elevationGain.Float64
	}

	redisKey := fmt.Sprintf("route_render:%s", routeID.String())
	cachedRenderJSON, redisErr := h.Redis.Get(r.Context(), redisKey).Result()
	if redisErr == nil && cachedRenderJSON != "" {
		var cachedResp routeRenderCachePayload
		if err := json.Unmarshal([]byte(cachedRenderJSON), &cachedResp); err == nil {
			resp := RouteRenderDataResponse{
				RouteID:        routeID,
				DistanceM:      cachedResp.DistanceM,
				ElevationGainM: cachedResp.ElevationGainM,
				ProfilePoints:  cachedResp.ProfilePoints,
			}
			if resp.DistanceM <= 0 {
				resp.DistanceM = distanceM
			}
			if resp.ElevationGainM <= 0 {
				resp.ElevationGainM = elevGain
			}
			if len(resp.ProfilePoints) < 2 {
				resp.ProfilePoints = []RenderPoint{{DistanceM: 0, ElevationM: 100}, {DistanceM: resp.DistanceM, ElevationM: 100 + resp.ElevationGainM}}
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(resp)
			return
		}
	}

	resp := RouteRenderDataResponse{
		RouteID:        routeID,
		DistanceM:      distanceM,
		ElevationGainM: elevGain,
		ProfilePoints:  []RenderPoint{{DistanceM: 0, ElevationM: 100}, {DistanceM: distanceM, ElevationM: 100 + elevGain}},
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(resp)
}
