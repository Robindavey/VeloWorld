.PHONY: dev test migrate clean build-backend build-pipeline prepare-env

# Start development environment
dev:
	docker-compose -f infra/docker-compose.yml up -d
	@echo "Development stack started. API available at http://localhost:8080"

# Prepare local environment
prepare-env:
	chmod +x scripts/prepare_env.sh && ./scripts/prepare_env.sh

# Run all tests
test: test-backend test-pipeline

# Run backend tests
test-backend:
	cd backend && go test ./...

# Run pipeline tests
test-pipeline:
	cd pipeline && python -m pytest tests/

# Run database migrations
migrate:
	docker-compose -f infra/docker-compose.yml exec -T postgres psql -U veloworld -d veloworld -f /docker-entrypoint-initdb.d/001_initial_schema.sql

# Clean up development environment
clean:
	docker-compose -f infra/docker-compose.yml down -v
	docker system prune -f

# Build backend Docker image
build-backend:
	docker build -f infra/Dockerfile.backend -t veloworld/backend .

# Build pipeline Docker image
build-pipeline:
	docker build -f infra/Dockerfile.pipeline -t veloworld/pipeline .

# View logs
logs:
	docker-compose -f infra/docker-compose.yml logs -f

# Run API integration tests
test-api:
	chmod +x test_api.sh && ./test_api.sh