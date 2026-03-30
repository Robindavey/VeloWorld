package auth

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
	"golang.org/x/crypto/bcrypt"
)

type Handler struct {
	DB    *sql.DB
	Redis *redis.Client
}

type RegisterRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	Name     string `json:"name,omitempty"`
	Bio      string `json:"bio,omitempty"`
}

type LoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type User struct {
	ID            uuid.UUID `json:"id"`
	Email         string    `json:"email"`
	Name          *string   `json:"name,omitempty"`
	Bio           *string   `json:"bio,omitempty"`
	RiderWeightKg float64   `json:"rider_weight_kg"`
	FtpW          float64   `json:"ftp_w"`
}

type UpdateProfileRequest struct {
	Name          *string  `json:"name"`
	Bio           *string  `json:"bio"`
	RiderWeightKg *float64 `json:"rider_weight_kg"`
	FtpW          *float64 `json:"ftp_w"`
}

type Claims struct {
	UserID uuid.UUID `json:"user_id"`
	Email  string    `json:"email"`
	jwt.RegisteredClaims
}

func NewHandler(db *sql.DB, redis *redis.Client) *Handler {
	return &Handler{DB: db, Redis: redis}
}

func (h *Handler) Register(w http.ResponseWriter, r *http.Request) {
	var req RegisterRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if req.Email == "" || req.Password == "" {
		http.Error(w, "Email and password are required", http.StatusBadRequest)
		return
	}

	// Hash password
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		http.Error(w, "Failed to hash password", http.StatusInternalServerError)
		return
	}

	// Create user
	userID := uuid.New()
	_, err = h.DB.Exec(`
		INSERT INTO users (id, email, password_hash, name, bio)
		VALUES ($1, $2, $3, $4, $5)`,
		userID, req.Email, string(hashedPassword), req.Name, req.Bio)
	if err != nil {
		if strings.Contains(err.Error(), "duplicate key") {
			http.Error(w, "Email already exists", http.StatusConflict)
			return
		}
		http.Error(w, "Failed to create user", http.StatusInternalServerError)
		return
	}

	// Generate JWT
	token, err := h.generateToken(userID, req.Email)
	if err != nil {
		http.Error(w, "Failed to generate token", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"token": token})
}

func (h *Handler) Login(w http.ResponseWriter, r *http.Request) {
	var req LoginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	// Get user
	var userID uuid.UUID
	var hashedPassword string
	err := h.DB.QueryRow(`
		SELECT id, password_hash FROM users WHERE email = $1`,
		req.Email).Scan(&userID, &hashedPassword)
	if err == sql.ErrNoRows {
		http.Error(w, "Invalid credentials", http.StatusUnauthorized)
		return
	}
	if err != nil {
		http.Error(w, "Database error", http.StatusInternalServerError)
		return
	}

	// Check password
	if err := bcrypt.CompareHashAndPassword([]byte(hashedPassword), []byte(req.Password)); err != nil {
		http.Error(w, "Invalid credentials", http.StatusUnauthorized)
		return
	}

	// Generate JWT
	token, err := h.generateToken(userID, req.Email)
	if err != nil {
		http.Error(w, "Failed to generate token", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"token": token})
}

func (h *Handler) GetCurrentUser(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	var email string
	var name sql.NullString
	var bio sql.NullString
	var riderWeightKg float64
	var ftpW float64
	err := h.DB.QueryRow("SELECT email, name, bio, rider_weight_kg, ftp_w FROM users WHERE id = $1", userID).
		Scan(&email, &name, &bio, &riderWeightKg, &ftpW)
	if err != nil {
		http.Error(w, "User not found", http.StatusNotFound)
		return
	}

	user := User{ID: userID, Email: email, RiderWeightKg: riderWeightKg, FtpW: ftpW}
	if name.Valid {
		user.Name = &name.String
	}
	if bio.Valid {
		user.Bio = &bio.String
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(user)
}

func (h *Handler) UpdateProfile(w http.ResponseWriter, r *http.Request) {
	userID, ok := r.Context().Value("user_id").(uuid.UUID)
	if !ok {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	var req UpdateProfileRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid request body", http.StatusBadRequest)
		return
	}

	if req.RiderWeightKg != nil && (*req.RiderWeightKg < 35 || *req.RiderWeightKg > 250) {
		http.Error(w, "Rider weight must be between 35kg and 250kg", http.StatusBadRequest)
		return
	}
	if req.FtpW != nil && (*req.FtpW < 80 || *req.FtpW > 600) {
		http.Error(w, "FTP must be between 80W and 600W", http.StatusBadRequest)
		return
	}

	_, err := h.DB.Exec(`
		UPDATE users
		SET name = COALESCE($1, name),
			bio = COALESCE($2, bio),
			rider_weight_kg = COALESCE($3, rider_weight_kg),
			ftp_w = COALESCE($4, ftp_w)
		WHERE id = $5`,
		req.Name, req.Bio, req.RiderWeightKg, req.FtpW, userID)
	if err != nil {
		http.Error(w, "Failed to update profile", http.StatusInternalServerError)
		return
	}

	h.GetCurrentUser(w, r)
}

func (h *Handler) generateToken(userID uuid.UUID, email string) (string, error) {
	secret := "development-secret-key-change-in-production" // TODO: Use env var
	if envSecret := os.Getenv("JWT_SECRET"); envSecret != "" {
		secret = envSecret
	}

	claims := Claims{
		UserID: userID,
		Email:  email,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(24 * time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(secret))
}
