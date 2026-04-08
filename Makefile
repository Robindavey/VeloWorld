.PHONY: dev test migrate clean build-backend build-pipeline prepare-env benchmark benchmark-backend benchmark-pipeline

PIPELINE_PYTHON := $(shell if [ -x $(CURDIR)/pipeline/.venv/bin/python ]; then echo $(CURDIR)/pipeline/.venv/bin/python; else echo python3; fi)

# Start development environment
dev:
	docker-compose -f infra/docker-compose.yml up -d
	@echo "Development stack started. API available at http://localhost:8080"

# Prepare local environment
prepare-env:
	chmod +x scripts/prepare_env.sh && ./scripts/prepare_env.sh

# Run all tests
test: test-backend test-pipeline

# Run strict benchmark gates and benchmark reports
benchmark: benchmark-backend benchmark-pipeline

# Run backend tests
test-backend:
	cd backend && go test ./...

# Run backend benchmark gates + benchmark report
benchmark-backend:
	cd backend && go test ./... -run "Budget" -bench "Benchmark" -benchmem

# Run pipeline tests
test-pipeline:
	cd pipeline && $(PIPELINE_PYTHON) -m pytest tests/

# Run pipeline performance budget tests only
benchmark-pipeline:
	cd pipeline && $(PIPELINE_PYTHON) -m pytest tests/test_performance_budgets.py -q

# Run database migrations
migrate:
	docker-compose -f infra/docker-compose.yml exec -T postgres psql -U veloverse -d veloverse -f /docker-entrypoint-initdb.d/001_initial_schema.sql
	docker-compose -f infra/docker-compose.yml exec -T postgres psql -U veloverse -d veloverse -f /docker-entrypoint-initdb.d/002_social_features.sql

# Clean up development environment
clean:
	docker-compose -f infra/docker-compose.yml down -v
	docker system prune -f

# Build backend Docker image
build-backend:
	docker build -f infra/Dockerfile.backend -t veloverse/backend .

# Build pipeline Docker image
build-pipeline:
	docker build -f infra/Dockerfile.pipeline -t veloverse/pipeline .

# View logs
logs:
	docker-compose -f infra/docker-compose.yml logs -f

# Run API integration tests
test-api:
	chmod +x test_api.sh && ./test_api.sh