# VeloVerse

VeloVerse is a next-generation indoor cycling simulator that converts real-world GPS route files into physics-accurate, procedurally-generated 3D cycling simulations. Users upload a GPX route, the platform reconstructs the terrain from LiDAR elevation data, generates a 3D environment, and delivers a rideable simulation with accurate gradient resistance communicated to a smart trainer in real time.

## Project Overview

This repository contains the complete VeloVerse MVP implementation, including:

- **Backend API** (Go): User accounts, route management, ride history, and route processing job system
- **Route Processing Pipeline** (Python): Converts GPX files into rideable 3D environments using LiDAR data and procedural generation
- **Client Application** (Unreal Engine 5 + C++): Real-time 3D rendering, physics simulation, and smart trainer integration
- **Infrastructure** (Docker): Complete development and deployment stack

## Local Development Setup

### Prerequisites

- Docker and Docker Compose
- Go 1.21+ (for backend development)
- Python 3.11+ (for pipeline development)
- Unreal Engine 5.3+ (for client development)
- Git

### Quick Start

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd veloverse
   ```

2. **Start the development stack:**
   ```bash
   make dev
   ```
   This starts PostgreSQL, Redis, MinIO (S3-compatible storage), the API backend, and pipeline workers.

3. **Run database migrations:**
   ```bash
   make migrate
   ```

4. **Verify the stack is running:**
   - API: http://localhost:8080/health
   - MinIO Console: http://localhost:9001 (admin/minioadmin)

### Development Workflow

- **Backend development:** Code in `backend/`, hot-reload with `go run cmd/api/main.go`
- **Pipeline development:** Code in `pipeline/`, test with `python -m pytest pipeline/tests/`
- **Client development:** Open `client/` in Unreal Engine 5
- **Database changes:** Add SQL files to `backend/db/migrations/`, run `make migrate`

## Running the Stack

### Development Mode
```bash
make dev
```
Starts all services with hot-reload and debugging enabled.

### Production Mode
```bash
docker-compose -f infra/docker-compose.yml up -d
```
Starts the stack in production configuration.

### Individual Services

- **PostgreSQL:** `docker-compose exec postgres psql -U veloverse -d veloverse`
- **Redis:** `docker-compose exec redis redis-cli`
- **API Backend:** `curl http://localhost:8080/health`
- **Pipeline Worker:** Logs available via `docker-compose logs pipeline-worker`

## Running Tests

### Unit Tests
```bash
make test
```
Runs all unit tests for backend and pipeline components.

### Strict Benchmark Gates
```bash
make benchmark
```
Runs hard performance-budget tests that fail on regressions and also prints benchmark metrics.

You can run each side separately:

```bash
make benchmark-backend
make benchmark-pipeline
```

Note: pipeline benchmark/test targets automatically use `pipeline/.venv/bin/python` when present.

### Backend Tests
```bash
cd backend
go test ./...
```

### Pipeline Tests
```bash
cd pipeline
python -m pytest
```

### API Integration Tests
```bash
make test-api
```
Runs comprehensive API endpoint tests including:
- User registration and authentication
- Route upload and management
- Ride creation and history
- Error handling and validation

### Manual API Testing
Use the provided test script:
```bash
./test_api.sh
```
This script tests all major API endpoints with realistic data and validates responses.

## Database Migrations

Migrations are stored as numbered SQL files in `backend/db/migrations/`.

To create a new migration:
1. Create a new file: `backend/db/migrations/NNN_description.sql`
2. Run: `make migrate`

## API Documentation

The API provides REST endpoints for user management, route upload/processing, and ride recording.

Key endpoints:
- `POST /auth/register` — User registration
- `POST /auth/login` — Authentication
- `POST /routes` — Upload GPX route
- `GET /routes` — List user routes
- `GET /routes/{id}` — Route details and processing status
- `POST /rides` — Record completed ride

Full API documentation available at `/docs` endpoint when running locally.

## Architecture

- **Backend:** Go with PostgreSQL and Redis
- **Pipeline:** Python with GDAL for geospatial processing
- **Client:** Unreal Engine 5 with custom C++ physics engine
- **Storage:** MinIO (S3-compatible) for route files and assets
- **Queue:** Redis-based job queue for route processing

## Contributing

1. Follow the established code style (gofmt for Go, black for Python)
2. Write tests for new functionality
3. Update documentation for API changes
4. Ensure all tests pass before submitting PRs

## License

Copyright 2024 VeloVerse. All rights reserved.