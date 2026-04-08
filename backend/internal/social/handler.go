package social

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/gorilla/mux"
)

type Handler struct {
	DB *sql.DB
}

type FollowRequestInput struct {
	UserID uuid.UUID `json:"user_id"`
}

type UserSummary struct {
	ID                 uuid.UUID `json:"id"`
	Email              string    `json:"email"`
	Name               *string   `json:"name,omitempty"`
	RelationshipStatus string    `json:"relationship_status,omitempty"`
}

type PublicRouteView struct {
	ID             uuid.UUID `json:"id"`
	Name           string    `json:"name"`
	Description    *string   `json:"description,omitempty"`
	DistanceM      float64   `json:"distance_m"`
	ElevationGainM *float64  `json:"elevation_gain_m,omitempty"`
	CreatedAt      string    `json:"created_at"`
	AuthorID       uuid.UUID `json:"author_id"`
	AuthorEmail    string    `json:"author_email"`
	AuthorName     *string   `json:"author_name,omitempty"`
}

type CollectionRouteView struct {
	RouteID        uuid.UUID   `json:"route_id"`
	Name           string      `json:"name"`
	Description    *string     `json:"description,omitempty"`
	DistanceM      float64     `json:"distance_m"`
	ElevationGainM *float64    `json:"elevation_gain_m,omitempty"`
	AddedAt        string      `json:"added_at"`
	OriginalAuthor UserSummary `json:"original_author"`
}

type IncomingFollowRequest struct {
	ID        uuid.UUID   `json:"id"`
	Requester UserSummary `json:"requester"`
	Status    string      `json:"status"`
	CreatedAt string      `json:"created_at"`
}

type OutgoingFollowRequest struct {
	ID       uuid.UUID   `json:"id"`
	Target   UserSummary `json:"target"`
	Status   string      `json:"status"`
	CreatedAt string     `json:"created_at"`
}

func NewHandler(db *sql.DB) *Handler {
	return &Handler{DB: db}
}

func (h *Handler) RequestFollow(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	var req FollowRequestInput
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}
	if req.UserID == uuid.Nil || req.UserID == userID {
		http.Error(w, "invalid follow target", http.StatusBadRequest)
		return
	}

	var existingRequester uuid.UUID
	var existingTarget uuid.UUID
	var existingStatus string
	existingErr := h.DB.QueryRow(`
		SELECT requester_id, target_id, status
		FROM follow_requests
		WHERE (requester_id = $1 AND target_id = $2)
			OR (requester_id = $2 AND target_id = $1)
		ORDER BY CASE status WHEN 'accepted' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, updated_at DESC
		LIMIT 1`, userID, req.UserID).Scan(&existingRequester, &existingTarget, &existingStatus)
	if existingErr != nil && existingErr != sql.ErrNoRows {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	if existingErr == nil {
		if existingStatus == "accepted" {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]any{"target_user_id": req.UserID, "status": "following"})
			return
		}

		if existingStatus == "pending" && existingRequester == req.UserID && existingTarget == userID {
			http.Error(w, "This user already requested to follow you. Check your incoming requests.", http.StatusConflict)
			return
		}

		if existingStatus == "pending" && existingRequester == userID && existingTarget == req.UserID {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]any{"target_user_id": req.UserID, "status": "pending"})
			return
		}
	}

	_, err := h.DB.Exec(`
		INSERT INTO follow_requests (requester_id, target_id, status)
		VALUES ($1, $2, 'pending')
		ON CONFLICT (requester_id, target_id)
		DO UPDATE SET status = 'pending', updated_at = NOW()
		WHERE follow_requests.status <> 'accepted'`, userID, req.UserID)
	if err != nil {
		http.Error(w, "Failed to create follow request", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]any{"target_user_id": req.UserID, "status": "pending"})
}

func (h *Handler) ListIncomingFollowRequests(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	rows, err := h.DB.Query(`
		SELECT fr.id, fr.status, fr.created_at, u.id, u.email, u.name
		FROM follow_requests fr
		JOIN users u ON u.id = fr.requester_id
		WHERE fr.target_id = $1 AND fr.status = 'pending'
		ORDER BY fr.created_at DESC`, userID)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var items []IncomingFollowRequest
	for rows.Next() {
		var item IncomingFollowRequest
		if err := rows.Scan(&item.ID, &item.Status, &item.CreatedAt, &item.Requester.ID, &item.Requester.Email, &item.Requester.Name); err != nil {
			http.Error(w, "Database error", http.StatusInternalServerError)
			return
		}
		items = append(items, item)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(items)
}

func (h *Handler) ListOutgoingFollowRequests(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	rows, err := h.DB.Query(`
		SELECT fr.id, fr.status, fr.created_at, u.id, u.email, u.name
		FROM follow_requests fr
		JOIN users u ON u.id = fr.target_id
		WHERE fr.requester_id = $1 AND fr.status = 'pending'
		ORDER BY fr.created_at DESC`, userID)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var items []OutgoingFollowRequest
	for rows.Next() {
		var item OutgoingFollowRequest
		if err := rows.Scan(&item.ID, &item.Status, &item.CreatedAt, &item.Target.ID, &item.Target.Email, &item.Target.Name); err != nil {
			http.Error(w, "Database error", http.StatusInternalServerError)
			return
		}
		items = append(items, item)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(items)
}

func (h *Handler) CancelOutgoingFollowRequest(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	targetID, err := uuid.Parse(mux.Vars(r)["id"])
	if err != nil {
		http.Error(w, "Invalid user ID", http.StatusBadRequest)
		return
	}

	result, err := h.DB.Exec(`
		DELETE FROM follow_requests
		WHERE requester_id = $1 AND target_id = $2 AND status = 'pending'`, userID, targetID)
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
		http.Error(w, "Pending follow request not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "cancelled"})
}

func (h *Handler) UnfollowUser(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	targetID, err := uuid.Parse(mux.Vars(r)["id"])
	if err != nil {
		http.Error(w, "Invalid user ID", http.StatusBadRequest)
		return
	}

	result, err := h.DB.Exec(`
		DELETE FROM follow_requests
		WHERE status = 'accepted'
		AND ((requester_id = $1 AND target_id = $2) OR (requester_id = $2 AND target_id = $1))`, userID, targetID)
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
		http.Error(w, "Follow relationship not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "unfollowed"})
}

func (h *Handler) UpdateFollowRequestStatus(w http.ResponseWriter, r *http.Request, nextStatus string) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	reqID, err := uuid.Parse(mux.Vars(r)["id"])
	if err != nil {
		http.Error(w, "Invalid request ID", http.StatusBadRequest)
		return
	}

	result, err := h.DB.Exec(`
		UPDATE follow_requests
		SET status = $1
		WHERE id = $2 AND target_id = $3 AND status = 'pending'`, nextStatus, reqID, userID)
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
		http.Error(w, "Follow request not found", http.StatusNotFound)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": nextStatus})
}

func (h *Handler) AcceptFollowRequest(w http.ResponseWriter, r *http.Request) {
	h.UpdateFollowRequestStatus(w, r, "accepted")
}

func (h *Handler) RejectFollowRequest(w http.ResponseWriter, r *http.Request) {
	h.UpdateFollowRequestStatus(w, r, "rejected")
}

func (h *Handler) SearchFollowers(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	q := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("q")))
	if len(q) < 1 {
		http.Error(w, "query param q is required", http.StatusBadRequest)
		return
	}

	rows, err := h.DB.Query(`
		SELECT DISTINCT u.id, u.email, u.name
		FROM users u
		JOIN follow_requests fr ON (
			(fr.requester_id = $1 AND fr.target_id = u.id)
			OR
			(fr.target_id = $1 AND fr.requester_id = u.id)
		)
		WHERE fr.status = 'accepted'
		AND (LOWER(u.email) LIKE '%' || $2 || '%' OR LOWER(COALESCE(u.name, '')) LIKE '%' || $2 || '%')
		ORDER BY u.email
		LIMIT 30`, userID, q)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var users []UserSummary
	for rows.Next() {
		var u UserSummary
		if err := rows.Scan(&u.ID, &u.Email, &u.Name); err != nil {
			http.Error(w, "Database error", http.StatusInternalServerError)
			return
		}
		users = append(users, u)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(users)
}

func (h *Handler) SearchUsers(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	q := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("q")))
	if len(q) < 1 {
		http.Error(w, "query param q is required", http.StatusBadRequest)
		return
	}

	rows, err := h.DB.Query(`
		WITH ranked_users AS (
			SELECT
				u.id,
				u.email,
				u.name,
				COALESCE((
					SELECT CASE
						WHEN fr.status = 'accepted' THEN 'following'
						WHEN fr.status = 'pending' AND fr.requester_id = $1 THEN 'pending_sent'
						WHEN fr.status = 'pending' AND fr.target_id = $1 THEN 'pending_received'
						ELSE fr.status
					END
					FROM follow_requests fr
					WHERE (fr.requester_id = $1 AND fr.target_id = u.id)
						OR (fr.requester_id = u.id AND fr.target_id = $1)
					ORDER BY CASE fr.status WHEN 'accepted' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, fr.updated_at DESC
					LIMIT 1
				), 'none') AS relationship_status,
				CASE
					WHEN LOWER(u.email) = $2 OR LOWER(COALESCE(u.name, '')) = $2 THEN 0
					WHEN LOWER(u.email) LIKE $2 || '%' OR LOWER(COALESCE(u.name, '')) LIKE $2 || '%' THEN 1
					WHEN LOWER(u.email) LIKE '%' || $2 || '%' OR LOWER(COALESCE(u.name, '')) LIKE '%' || $2 || '%' THEN 2
					ELSE 3
				END AS search_rank
			FROM users u
			WHERE u.id <> $1
			AND (
				LOWER(u.email) LIKE '%' || $2 || '%'
				OR LOWER(COALESCE(u.name, '')) LIKE '%' || $2 || '%'
			)
		)
		SELECT id, email, name, relationship_status, search_rank
		FROM ranked_users
		ORDER BY
			CASE relationship_status
				WHEN 'following' THEN 0
				WHEN 'pending_received' THEN 1
				WHEN 'pending_sent' THEN 2
				ELSE 3
			END,
			search_rank,
			email
		LIMIT 30`, userID, q)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var users []UserSummary
	for rows.Next() {
		var u UserSummary
		var searchRank int
		if err := rows.Scan(&u.ID, &u.Email, &u.Name, &u.RelationshipStatus, &searchRank); err != nil {
			http.Error(w, "Database error", http.StatusInternalServerError)
			return
		}
		users = append(users, u)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(users)
}

func (h *Handler) ListUserPublicRoutes(w http.ResponseWriter, r *http.Request) {
	viewerID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	targetID, err := uuid.Parse(mux.Vars(r)["id"])
	if err != nil {
		http.Error(w, "Invalid user ID", http.StatusBadRequest)
		return
	}

	if viewerID != targetID {
		var allowed bool
		err = h.DB.QueryRow(`
			SELECT EXISTS(
				SELECT 1 FROM follow_requests fr
				WHERE fr.status = 'accepted'
				AND ((fr.requester_id = $1 AND fr.target_id = $2) OR (fr.requester_id = $2 AND fr.target_id = $1))
			)`, viewerID, targetID).Scan(&allowed)
		if err != nil {
			http.Error(w, "Database error", http.StatusInternalServerError)
			return
		}
		if !allowed {
			http.Error(w, "Follow relationship required", http.StatusForbidden)
			return
		}
	}

	rows, err := h.DB.Query(`
		SELECT r.id, r.name, r.description, r.distance_m, r.elevation_gain_m, r.created_at,
				u.id, u.email, u.name
		FROM routes r
		JOIN users u ON u.id = r.owner_id
		WHERE r.owner_id = $1 AND r.is_public = true AND r.processing_status = 'ready'
		ORDER BY r.created_at DESC`, targetID)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var routes []PublicRouteView
	for rows.Next() {
		var item PublicRouteView
		if err := rows.Scan(&item.ID, &item.Name, &item.Description, &item.DistanceM, &item.ElevationGainM, &item.CreatedAt,
			&item.AuthorID, &item.AuthorEmail, &item.AuthorName); err != nil {
			http.Error(w, "Database error", http.StatusInternalServerError)
			return
		}
		routes = append(routes, item)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(routes)
}

func (h *Handler) AddRouteToCollection(w http.ResponseWriter, r *http.Request) {
	collectorID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	routeID, err := uuid.Parse(mux.Vars(r)["id"])
	if err != nil {
		http.Error(w, "Invalid route ID", http.StatusBadRequest)
		return
	}

	var ownerID uuid.UUID
	var isPublic bool
	err = h.DB.QueryRow(`SELECT owner_id, is_public FROM routes WHERE id = $1 AND processing_status = 'ready'`, routeID).Scan(&ownerID, &isPublic)
	if err == sql.ErrNoRows {
		http.Error(w, "Route not found", http.StatusNotFound)
		return
	}
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	if ownerID != collectorID {
		if !isPublic {
			http.Error(w, "Only public routes can be collected", http.StatusForbidden)
			return
		}

		var allowed bool
		err = h.DB.QueryRow(`
			SELECT EXISTS(
				SELECT 1 FROM follow_requests fr
				WHERE fr.status = 'accepted'
				AND ((fr.requester_id = $1 AND fr.target_id = $2) OR (fr.requester_id = $2 AND fr.target_id = $1))
			)`, collectorID, ownerID).Scan(&allowed)
		if err != nil {
			http.Error(w, "Database error", http.StatusInternalServerError)
			return
		}
		if !allowed {
			http.Error(w, "Follow relationship required", http.StatusForbidden)
			return
		}
	}

	_, err = h.DB.Exec(`
		INSERT INTO route_collections (collector_id, route_id)
		VALUES ($1, $2)
		ON CONFLICT (collector_id, route_id) DO NOTHING`, collectorID, routeID)
	if err != nil {
		http.Error(w, "Failed to add route to collection", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{"route_id": routeID, "status": "saved"})
}

func (h *Handler) ListCollection(w http.ResponseWriter, r *http.Request) {
	collectorID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	rows, err := h.DB.Query(`
		SELECT r.id, r.name, r.description, r.distance_m, r.elevation_gain_m, rc.added_at,
				u.id, u.email, u.name
		FROM route_collections rc
		JOIN routes r ON r.id = rc.route_id
		JOIN users u ON u.id = r.owner_id
		WHERE rc.collector_id = $1
		ORDER BY rc.added_at DESC`, collectorID)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var items []CollectionRouteView
	for rows.Next() {
		var item CollectionRouteView
		if err := rows.Scan(&item.RouteID, &item.Name, &item.Description, &item.DistanceM, &item.ElevationGainM, &item.AddedAt,
			&item.OriginalAuthor.ID, &item.OriginalAuthor.Email, &item.OriginalAuthor.Name); err != nil {
			http.Error(w, "Database error", http.StatusInternalServerError)
			return
		}
		items = append(items, item)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(items)
}
