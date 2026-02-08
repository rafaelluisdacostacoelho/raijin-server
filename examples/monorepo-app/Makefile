.PHONY: help dev stop logs build-all test-all lint clean deploy-tst deploy-prd

REGISTRY ?= harbor.asgard.local
PROJECT  ?= tst
TAG      ?= dev

# ============================================================================
# Help
# ============================================================================
help:
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════╗"
	@echo "║             Monorepo Template — Comandos                   ║"
	@echo "╠══════════════════════════════════════════════════════════════╣"
	@echo "║                                                            ║"
	@echo "║  Development:                                              ║"
	@echo "║    make dev              Start all services (docker)       ║"
	@echo "║    make dev-web          Start only frontend React         ║"
	@echo "║    make dev-api          Start API Go + deps               ║"
	@echo "║    make logs             Follow all logs                   ║"
	@echo "║    make stop             Stop all services                 ║"
	@echo "║                                                            ║"
	@echo "║  Build:                                                    ║"
	@echo "║    make build-all        Build all Docker images           ║"
	@echo "║    make build-web        Build frontend image              ║"
	@echo "║    make build-api-go     Build Go API image                ║"
	@echo "║    make build-api-py     Build Python API image            ║"
	@echo "║    make build-api-dotnet Build .NET API image              ║"
	@echo "║                                                            ║"
	@echo "║  Test:                                                     ║"
	@echo "║    make test-all         Run all tests                     ║"
	@echo "║    make test-web         Run frontend tests                ║"
	@echo "║    make test-api-go      Run Go API tests                  ║"
	@echo "║    make test-api-py      Run Python API tests              ║"
	@echo "║    make lint             Run all linters                   ║"
	@echo "║                                                            ║"
	@echo "║  Deploy:                                                   ║"
	@echo "║    make deploy-tst       Deploy to TST                     ║"
	@echo "║    make deploy-prd       Deploy to PRD                     ║"
	@echo "║                                                            ║"
	@echo "║  Utilities:                                                ║"
	@echo "║    make clean            Remove containers + volumes       ║"
	@echo "║    make db-shell         Open psql shell                   ║"
	@echo "║                                                            ║"
	@echo "╚══════════════════════════════════════════════════════════════╝"
	@echo ""

# ============================================================================
# Development
# ============================================================================
dev:
	docker compose up -d
	@echo ""
	@echo "Services:"
	@echo "  Frontend (React):  http://localhost:5173"
	@echo "  API Go:            http://localhost:8080"
	@echo "  API Python:        http://localhost:8081"
	@echo "  API .NET:          http://localhost:8082"
	@echo "  MailHog:           http://localhost:8025"
	@echo "  Adminer:           http://localhost:8181"
	@echo ""
	@echo "Demo login: admin@example.com / admin123"

dev-web:
	cd frontends/meu-app-web && npm run dev

dev-api:
	docker compose up -d postgres redis
	cd backends/api-go && go run ./cmd/server

logs:
	docker compose logs -f

stop:
	docker compose down

# ============================================================================
# Build
# ============================================================================
build-web:
	docker build -t $(REGISTRY)/$(PROJECT)/meu-app-web:$(TAG) ./frontends/meu-app-web
	@echo "Built: $(REGISTRY)/$(PROJECT)/meu-app-web:$(TAG)"

build-api-go:
	docker build -t $(REGISTRY)/$(PROJECT)/api-go:$(TAG) ./backends/api-go
	@echo "Built: $(REGISTRY)/$(PROJECT)/api-go:$(TAG)"

build-api-py:
	docker build -t $(REGISTRY)/$(PROJECT)/api-python:$(TAG) ./backends/api-python
	@echo "Built: $(REGISTRY)/$(PROJECT)/api-python:$(TAG)"

build-api-dotnet:
	docker build -t $(REGISTRY)/$(PROJECT)/api-dotnet:$(TAG) ./backends/api-dotnet
	@echo "Built: $(REGISTRY)/$(PROJECT)/api-dotnet:$(TAG)"

build-all: build-web build-api-go build-api-py build-api-dotnet
	@echo "All images built"

push-all:
	docker push $(REGISTRY)/$(PROJECT)/meu-app-web:$(TAG)
	docker push $(REGISTRY)/$(PROJECT)/api-go:$(TAG)
	docker push $(REGISTRY)/$(PROJECT)/api-python:$(TAG)
	docker push $(REGISTRY)/$(PROJECT)/api-dotnet:$(TAG)
	@echo "All images pushed"

# ============================================================================
# Test
# ============================================================================
test-web:
	cd frontends/meu-app-web && npm run test:coverage

test-api-go:
	cd backends/api-go && go test -v -race -coverprofile=coverage.out ./...
	cd backends/api-go && go tool cover -func=coverage.out

test-api-py:
	cd backends/api-python && python -m pytest tests/ -v --cov=app --cov-report=term-missing

test-all: test-web test-api-go test-api-py
	@echo "All tests passed"

lint:
	cd frontends/meu-app-web && npm run lint
	cd backends/api-go && golangci-lint run ./...
	cd backends/api-python && ruff check .
	@echo "All linters passed"

# ============================================================================
# Deploy
# ============================================================================
deploy-tst:
	@echo "Deploying to TST..."
	kubectl apply -k kubernetes/overlays/tst
	kubectl rollout status deployment/meu-app-web -n app-tst --timeout=5m
	kubectl rollout status deployment/api-go -n app-tst --timeout=5m
	@echo "TST deployment complete"

deploy-prd:
	@echo "Deploying to PRODUCTION..."
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	kubectl apply -k kubernetes/overlays/prd
	kubectl rollout status deployment/meu-app-web -n app-prd --timeout=10m
	kubectl rollout status deployment/api-go -n app-prd --timeout=10m
	@echo "PRD deployment complete"

# ============================================================================
# Utilities
# ============================================================================
clean:
	docker compose down -v --remove-orphans
	rm -rf frontends/meu-app-web/node_modules frontends/meu-app-web/dist
	rm -rf frontends/meu-app-admin/node_modules frontends/meu-app-admin/dist
	rm -rf backends/api-go/tmp backends/api-go/coverage.out
	@echo "Cleaned up"

db-shell:
	docker compose exec postgres psql -U app -d appdb
