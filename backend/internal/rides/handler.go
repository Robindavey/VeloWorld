package rides

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/gorilla/mux"
	"github.com/redis/go-redis/v9"
)

type Handler struct {
	DB    *sql.DB
	Redis *redis.Client
}

type Ride struct {
	ID             uuid.UUID `json:"id"`
	RiderID        uuid.UUID `json:"rider_id"`
	RouteID        *uuid.UUID `json:"route_id,omitempty"`
	StartedAt      string     `json:"started_at"`
	CompletedAt    *string    `json:"completed_at,omitempty"`
	DurationS      *int       `json:"duration_s,omitempty"`
	DistanceM      *float64   `json:"distance_m,omitempty"`
	ElevationGainM *float64   `json:"elevation_gain_m,omitempty"`
	AvgPowerW      *float64   `json:"avg_power_w,omitempty"`
	AvgSpeedKph    *float64   `json:"avg_speed_kph,omitempty"`
	MaxPowerW      *float64   `json:"max_power_w,omitempty"`
	MaxSpeedKph    *float64   `json:"max_speed_kph,omitempty"`
	TotalEnergyKj  *float64   `json:"total_energy_kj,omitempty"`
}

type CreateRideRequest struct {
	RouteID        *uuid.UUID `json:"route_id,omitempty"`
	DurationS      int        `json:"duration_s"`
	DistanceM      float64    `json:"distance_m"`
	ElevationGainM float64    `json:"elevation_gain_m"`
	AvgPowerW      float64    `json:"avg_power_w"`
	AvgSpeedKph    float64    `json:"avg_speed_kph"`
	MaxPowerW      float64    `json:"max_power_w"`
	MaxSpeedKph    float64    `json:"max_speed_kph"`
	TotalEnergyKj  float64    `json:"total_energy_kj"`
}

func NewHandler(db *sql.DB, redis *redis.Client) *Handler {
	return &Handler{DB: db, Redis: redis}
}

func stringPtr(s string) *string {
	return &s
}

func (h *Handler) CreateRide(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	var req CreateRideRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Validate required fields
	if req.DurationS <= 0 || req.DistanceM <= 0 {
		http.Error(w, "Duration and distance are required and must be positive", http.StatusBadRequest)
		return
	}

	// If route_id is provided, verify ownership
	if req.RouteID != nil {
		var ownerID uuid.UUID
		err := h.DB.QueryRow("SELECT owner_id FROM routes WHERE id = $1", *req.RouteID).Scan(&ownerID)
		if err == sql.ErrNoRows {
			http.Error(w, "Route not found", http.StatusBadRequest)
			return
		}
		if err != nil {
			http.Error(w, "Database error", http.StatusInternalServerError)
			return
		}
		if ownerID != userID {
			http.Error(w, "Route does not belong to user", http.StatusForbidden)
			return
		}
	}

	// Create ride record
	rideID := uuid.New()
	now := time.Now()
	completedAt := now

	_, err := h.DB.Exec(`
		INSERT INTO rides (
			id, rider_id, route_id, started_at, completed_at, duration_s,
			distance_m, elevation_gain_m, avg_power_w, avg_speed_kph,
			max_power_w, max_speed_kph, total_energy_kj
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)`,
		rideID, userID, req.RouteID, now.Add(-time.Duration(req.DurationS)*time.Second),
		completedAt, req.DurationS, req.DistanceM, req.ElevationGainM,
		req.AvgPowerW, req.AvgSpeedKph, req.MaxPowerW, req.MaxSpeedKph, req.TotalEnergyKj)
	if err != nil {
		http.Error(w, "Failed to create ride", http.StatusInternalServerError)
		return
	}

	ride := Ride{
		ID:             rideID,
		RiderID:        userID,
		RouteID:        req.RouteID,
		StartedAt:      now.Add(-time.Duration(req.DurationS) * time.Second).Format(time.RFC3339),
		CompletedAt:    stringPtr(completedAt.Format(time.RFC3339)),
		DurationS:      &req.DurationS,
		DistanceM:      &req.DistanceM,
		ElevationGainM: &req.ElevationGainM,
		AvgPowerW:      &req.AvgPowerW,
		AvgSpeedKph:    &req.AvgSpeedKph,
		MaxPowerW:      &req.MaxPowerW,
		MaxSpeedKph:    &req.MaxSpeedKph,
		TotalEnergyKj:  &req.TotalEnergyKj,
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(ride)
}

func (h *Handler) ListRides(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	rows, err := h.DB.Query(`
		SELECT id, rider_id, route_id, started_at, completed_at, duration_s,
			   distance_m, elevation_gain_m, avg_power_w, avg_speed_kph,
			   max_power_w, max_speed_kph, total_energy_kj
		FROM rides
		WHERE rider_id = $1
		ORDER BY started_at DESC
		LIMIT 100`,
		userID)
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var rides []Ride
	for rows.Next() {
		var ride Ride
		var completedAt sql.NullString
		err := rows.Scan(&ride.ID, &ride.RiderID, &ride.RouteID, &ride.StartedAt,
			&completedAt, &ride.DurationS, &ride.DistanceM, &ride.ElevationGainM,
			&ride.AvgPowerW, &ride.AvgSpeedKph, &ride.MaxPowerW, &ride.MaxSpeedKph, &ride.TotalEnergyKj)
		if err != nil {
			http.Error(w, "Database error", http.StatusInternalServerError)
			return
		}
		if completedAt.Valid {
			ride.CompletedAt = &completedAt.String
		}
		rides = append(rides, ride)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(rides)
}

func (h *Handler) GetRide(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	vars := mux.Vars(r)
	rideIDStr := vars["id"]
	rideID, err := uuid.Parse(rideIDStr)
	if err != nil {
		http.Error(w, "Invalid ride ID", http.StatusBadRequest)
		return
	}

	var ride Ride
	var completedAt sql.NullString
	err = h.DB.QueryRow(`
		SELECT id, rider_id, route_id, started_at, completed_at, duration_s,
			   distance_m, elevation_gain_m, avg_power_w, avg_speed_kph,
			   max_power_w, max_speed_kph, total_energy_kj
		FROM rides
		WHERE id = $1 AND rider_id = $2`,
		rideID, userID).Scan(&ride.ID, &ride.RiderID, &ride.RouteID, &ride.StartedAt,
		&completedAt, &ride.DurationS, &ride.DistanceM, &ride.ElevationGainM,
		&ride.AvgPowerW, &ride.AvgSpeedKph, &ride.MaxPowerW, &ride.MaxSpeedKph, &ride.TotalEnergyKj)

	if err == sql.ErrNoRows {
		http.Error(w, "Ride not found", http.StatusNotFound)
		return
	}
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	if completedAt.Valid {
		ride.CompletedAt = &completedAt.String
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(ride)
}