package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/gorilla/mux"
	_ "github.com/lib/pq"
	"github.com/redis/go-redis/v9"
	"github.com/veloworld/backend/internal/auth"
	"github.com/veloworld/backend/internal/middleware"
	"github.com/veloworld/backend/internal/queue"
	"github.com/veloworld/backend/internal/rides"
	"github.com/veloworld/backend/internal/routes"
	"github.com/veloworld/backend/internal/storage"
)

type App struct {
	DB           *sql.DB
	Redis        *redis.Client
	Storage      *storage.S3Storage
	Queue        *queue.JobQueue
	Router       *mux.Router
	AuthHandler  *auth.Handler
	RouteHandler *routes.Handler
	RideHandler  *rides.Handler
}

func (a *App) Initialize() error {
	ctx := context.Background()

	// Database connection
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgresql://veloworld:veloworld@localhost:5432/veloworld?sslmode=disable"
	}

	var err error
	a.DB, err = sql.Open("postgres", dbURL)
	if err != nil {
		return fmt.Errorf("failed to connect to database: %v", err)
	}

	if err := a.DB.Ping(); err != nil {
		return fmt.Errorf("failed to ping database: %v", err)
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
		s3Config.Bucket = "veloworld"
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

	// Route routes (protected)
	protected := a.Router.PathPrefix("/").Subrouter()
	protected.Use(middleware.AuthMiddleware)
	protected.HandleFunc("/routes", a.RouteHandler.UploadRoute).Methods("POST")
	protected.HandleFunc("/routes", a.RouteHandler.ListRoutes).Methods("GET")
	protected.HandleFunc("/routes/{id}", a.RouteHandler.GetRoute).Methods("GET")
	protected.HandleFunc("/routes/{id}", a.RouteHandler.DeleteRoute).Methods("DELETE")
	protected.HandleFunc("/routes/public", a.RouteHandler.ListPublicRoutes).Methods("GET")
	protected.HandleFunc("/routes/{id}/publish", a.RouteHandler.PublishRoute).Methods("POST")
	protected.HandleFunc("/routes/{id}/package", a.RouteHandler.GetRoutePackage).Methods("GET")

	// Ride routes (protected)
	protected.HandleFunc("/rides", a.RideHandler.CreateRide).Methods("POST")
	protected.HandleFunc("/rides", a.RideHandler.ListRides).Methods("GET")
	protected.HandleFunc("/rides/{id}", a.RideHandler.GetRide).Methods("GET")
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
