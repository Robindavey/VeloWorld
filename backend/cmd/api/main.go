package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"

	"github.com/gorilla/mux"
	_ "github.com/lib/pq"
	"github.com/redis/go-redis/v9"
	"github.com/veloverse/backend/internal/auth"
	"github.com/veloverse/backend/internal/middleware"
	"github.com/veloverse/backend/internal/queue"
	"github.com/veloverse/backend/internal/rides"
	"github.com/veloverse/backend/internal/routes"
	"github.com/veloverse/backend/internal/social"
	"github.com/veloverse/backend/internal/storage"
)

type App struct {
	DB            *sql.DB
	Redis         *redis.Client
	Storage       *storage.S3Storage
	Queue         *queue.JobQueue
	Router        *mux.Router
	AuthHandler   *auth.Handler
	RouteHandler  *routes.Handler
	RideHandler   *rides.Handler
	SocialHandler *social.Handler
}

func ensureSocialSchema(db *sql.DB) error {
	statements := []string{
		`CREATE EXTENSION IF NOT EXISTS pgcrypto`,
		`CREATE EXTENSION IF NOT EXISTS pg_trgm`,
		`CREATE TABLE IF NOT EXISTS follow_requests (
			id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
			requester_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
			target_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
			status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
			created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
			updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
			UNIQUE (requester_id, target_id)
		)`,
		`CREATE INDEX IF NOT EXISTS idx_follow_requests_target_status ON follow_requests(target_id, status)`,
		`CREATE INDEX IF NOT EXISTS idx_follow_requests_pair_status ON follow_requests(requester_id, target_id, status)`,
		`CREATE TABLE IF NOT EXISTS route_collections (
			collector_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
			route_id UUID NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
			added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
			PRIMARY KEY (collector_id, route_id)
		)`,
		`CREATE INDEX IF NOT EXISTS idx_route_collections_collector_added ON route_collections(collector_id, added_at DESC)`,
	}

	for _, stmt := range statements {
		if _, err := db.Exec(stmt); err != nil {
			return err
		}
	}

	return nil
}

func buildDatabaseURLCandidates(primary string) []string {
	candidates := []string{primary}
	seen := map[string]bool{primary: true}

	add := func(v string) {
		if v == "" || seen[v] {
			return
		}
		seen[v] = true
		candidates = append(candidates, v)
	}

	if strings.Contains(primary, "veloverse:veloverse") || strings.Contains(primary, "/veloverse") {
		legacy := strings.ReplaceAll(primary, "veloverse:veloverse", "veloworld:veloworld")
		legacy = strings.ReplaceAll(legacy, "/veloverse?", "/veloworld?")
		if strings.HasSuffix(legacy, "/veloverse") {
			legacy = strings.TrimSuffix(legacy, "/veloverse") + "/veloworld"
		}
		add(legacy)
	}

	if strings.Contains(primary, "veloworld:veloworld") || strings.Contains(primary, "/veloworld") {
		modern := strings.ReplaceAll(primary, "veloworld:veloworld", "veloverse:veloverse")
		modern = strings.ReplaceAll(modern, "/veloworld?", "/veloverse?")
		if strings.HasSuffix(modern, "/veloworld") {
			modern = strings.TrimSuffix(modern, "/veloworld") + "/veloverse"
		}
		add(modern)
	}

	return candidates
}

func (a *App) Initialize() error {
	ctx := context.Background()

	// Database connection
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgres://veloverse:veloverse@postgres:5432/veloverse?sslmode=disable&connect_timeout=10"
	}

	var err error
	var lastDBErr error
	for _, candidate := range buildDatabaseURLCandidates(dbURL) {
		db, openErr := sql.Open("postgres", candidate)
		if openErr != nil {
			lastDBErr = openErr
			continue
		}

		if pingErr := db.Ping(); pingErr != nil {
			lastDBErr = pingErr
			_ = db.Close()
			continue
		}

		a.DB = db
		if candidate != dbURL {
			log.Printf("Database primary DSN failed, using fallback DSN")
		}
		lastDBErr = nil
		break
	}

	if lastDBErr != nil || a.DB == nil {
		return fmt.Errorf("failed to ping database: %v", lastDBErr)
	}

	if err := ensureSocialSchema(a.DB); err != nil {
		return fmt.Errorf("failed to ensure social schema: %v", err)
	}

	// Redis connection
	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://localhost:6379"
	}

	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return fmt.Errorf("failed to parse Redis URL: %v", err)
	}

	a.Redis = redis.NewClient(opt)
	if err := a.Redis.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("failed to connect to Redis: %v", err)
	}

	// Initialize S3 storage
	s3Config := storage.Config{
		Endpoint:  os.Getenv("S3_ENDPOINT"),
		AccessKey: os.Getenv("S3_ACCESS_KEY"),
		SecretKey: os.Getenv("S3_SECRET_KEY"),
		Bucket:    os.Getenv("S3_BUCKET"),
		BasePath:  os.Getenv("S3_BASE_PATH"),
		UseSSL:    os.Getenv("S3_USE_SSL") != "false", // Default to true
	}
	if s3Config.Endpoint == "" {
		s3Config.Endpoint = "http://localhost:9000"
	}
	if s3Config.AccessKey == "" {
		s3Config.AccessKey = "minioadmin"
	}
	if s3Config.SecretKey == "" {
		s3Config.SecretKey = "minioadmin"
	}
	if s3Config.Bucket == "" {
		s3Config.Bucket = "veloverse"
	}
	if s3Config.BasePath == "" {
		s3Config.BasePath = "uploads"
	}

	a.Storage, err = storage.NewS3Storage(s3Config)
	if err != nil {
		return fmt.Errorf("failed to initialize S3 storage: %v", err)
	}

	// Initialize job queue
	a.Queue = queue.NewJobQueue(a.Redis)

	a.Router = mux.NewRouter()

	// CORS middleware
	a.Router.Use(func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Access-Control-Allow-Origin", "*")
			w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
			if r.Method == "OPTIONS" {
				w.WriteHeader(http.StatusOK)
				return
			}
			next.ServeHTTP(w, r)
		})
	})

	a.AuthHandler = auth.NewHandler(a.DB, a.Redis)
	a.RouteHandler = routes.NewHandler(a.DB, a.Redis, a.Storage, a.Queue)
	a.RideHandler = rides.NewHandler(a.DB, a.Redis)
	a.SocialHandler = social.NewHandler(a.DB)

	a.initializeRoutes()

	return nil
}

func (a *App) initializeRoutes() {
	// Health check
	a.Router.HandleFunc("/health", a.healthCheck).Methods("GET")

	// Auth routes
	a.Router.HandleFunc("/auth/register", a.AuthHandler.Register).Methods("POST")
	a.Router.HandleFunc("/auth/login", a.AuthHandler.Login).Methods("POST")
	a.Router.Handle("/auth/me", middleware.AuthMiddleware(http.HandlerFunc(a.AuthHandler.GetCurrentUser))).Methods("GET")
	a.Router.Handle("/auth/profile", middleware.AuthMiddleware(http.HandlerFunc(a.AuthHandler.UpdateProfile))).Methods("PUT")
	a.Router.Handle("/auth/password", middleware.AuthMiddleware(http.HandlerFunc(a.AuthHandler.ChangePassword))).Methods("PUT")

	// Route routes (protected)
	protected := a.Router.PathPrefix("/").Subrouter()
	protected.Use(middleware.AuthMiddleware)
	protected.HandleFunc("/routes", a.RouteHandler.UploadRoute).Methods("POST")
	protected.HandleFunc("/routes", a.RouteHandler.ListRoutes).Methods("GET")
	protected.HandleFunc("/routes/{id}", a.RouteHandler.GetRoute).Methods("GET")
	protected.HandleFunc("/routes/{id}", a.RouteHandler.DeleteRoute).Methods("DELETE")
	protected.HandleFunc("/routes/{id}/render-data", a.RouteHandler.GetRouteRenderData).Methods("GET")
	protected.HandleFunc("/routes/public", a.RouteHandler.ListPublicRoutes).Methods("GET")
	protected.HandleFunc("/routes/{id}/publish", a.RouteHandler.PublishRoute).Methods("POST")
	protected.HandleFunc("/routes/{id}/visibility", a.RouteHandler.UpdateVisibility).Methods("PUT")
	protected.HandleFunc("/routes/{id}/retry", a.RouteHandler.RetryRouteProcessing).Methods("POST")
	protected.HandleFunc("/routes/{id}/package", a.RouteHandler.GetRoutePackage).Methods("GET")

	// Ride routes (protected)
	protected.HandleFunc("/rides", a.RideHandler.CreateRide).Methods("POST")
	protected.HandleFunc("/rides", a.RideHandler.ListRides).Methods("GET")
	protected.HandleFunc("/rides/{id}", a.RideHandler.GetRide).Methods("GET")

	// Social routes (protected)
	protected.HandleFunc("/social/users/search", a.SocialHandler.SearchUsers).Methods("GET")
	protected.HandleFunc("/social/follows/requests", a.SocialHandler.RequestFollow).Methods("POST")
	protected.HandleFunc("/social/follows/requests", a.SocialHandler.ListIncomingFollowRequests).Methods("GET")
	protected.HandleFunc("/social/follows/requests/outgoing", a.SocialHandler.ListOutgoingFollowRequests).Methods("GET")
	protected.HandleFunc("/social/follows/requests/{id}", a.SocialHandler.CancelOutgoingFollowRequest).Methods("DELETE")
	protected.HandleFunc("/social/follows/{id}", a.SocialHandler.UnfollowUser).Methods("DELETE")
	protected.HandleFunc("/social/follows/requests/{id}/accept", a.SocialHandler.AcceptFollowRequest).Methods("POST")
	protected.HandleFunc("/social/follows/requests/{id}/reject", a.SocialHandler.RejectFollowRequest).Methods("POST")
	protected.HandleFunc("/social/followers/search", a.SocialHandler.SearchFollowers).Methods("GET")
	protected.HandleFunc("/social/users/{id}/routes/public", a.SocialHandler.ListUserPublicRoutes).Methods("GET")
	protected.HandleFunc("/social/routes/{id}/collect", a.SocialHandler.AddRouteToCollection).Methods("POST")
	protected.HandleFunc("/social/collections", a.SocialHandler.ListCollection).Methods("GET")
}

func (a *App) Run(addr string) {
	// Wrap the router so we always set CORS headers, including for 405/404 responses.
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusOK)
			return
		}
		a.Router.ServeHTTP(w, r)
	})

	log.Printf("Server starting on %s", addr)
	log.Fatal(http.ListenAndServe(addr, handler))
}

func (a *App) healthCheck(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{"status": "healthy"})
}

func main() {
	app := &App{}
	if err := app.Initialize(); err != nil {
		log.Fatal(err)
	}
	app.Run(":8080")
}
