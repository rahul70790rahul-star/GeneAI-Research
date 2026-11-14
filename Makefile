# GeneAI Research - Makefile for Common Tasks

.PHONY: help install test lint typecheck format run build deploy clean

# Default target
help:
	@echo "GeneAI Research - Available Commands:"
	@echo ""
	@echo "Development:"
	@echo "  make install        - Install dependencies"
	@echo "  make run            - Run Streamlit app locally"
	@echo "  make run-dev        - Run with auto-reload"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run all tests"
	@echo "  make test-unit      - Run unit tests only"
	@echo "  make test-integration - Run integration tests"
	@echo "  make test-smoke     - Run smoke tests"
	@echo "  make test-coverage  - Run tests with coverage"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint           - Run Ruff linter"
	@echo "  make format         - Format code with Ruff"
	@echo "  make typecheck      - Run MyPy type checking"
	@echo "  make check          - Run all checks (lint, typecheck, test)"
	@echo ""
	@echo "Docker:"
	@echo "  make build          - Build Docker image"
	@echo "  make build-staging  - Build for staging"
	@echo "  make build-prod     - Build for production"
	@echo "  make up             - Start services with docker-compose"
	@echo "  make down           - Stop services"
	@echo "  make logs           - View logs"
	@echo ""
	@echo "Deployment:"
	@echo "  make deploy-staging - Deploy to staging"
	@echo "  make deploy-prod    - Deploy to production"
	@echo "  make rollback-staging - Rollback staging"
	@echo "  make backup-staging - Backup staging database"
	@echo ""
	@echo "Database:"
	@echo "  make db-shell       - Open PostgreSQL shell"
	@echo "  make db-backup      - Backup database"
	@echo "  make db-restore     - Restore database"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean          - Clean build artifacts"
	@echo "  make clean-all      - Clean everything including volumes"

# Install dependencies
install:
	pip install --upgrade pip
	pip install -r requirements.txt
	pip install -e .

install-dev: install
	pip install pytest pytest-cov pytest-mock ruff mypy bandit safety

# Run application
run:
	streamlit run app.py --server.port=8501 --server.address=0.0.0.0

run-dev:
	streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.runOnSave=true

# Testing
test:
	python -m pytest tests/ -v --tb=short

test-unit:
	python -m pytest tests/ -m "unit" -v --tb=short

test-integration:
	python -m pytest tests/test_integration.py -v --tb=short

test-smoke:
	python -m pytest tests/test_smoke.py -v --tb=short

test-coverage:
	python -m pytest tests/ --cov=geneai --cov-report=term-missing --cov-report=html

test-performance:
	python -m pytest tests/test_performance.py -v --tb=short

test-cloud:
	python -m pytest tests/test_cloud_integration.py -v --tb=short

# Code Quality
lint:
	ruff check geneai/ tests/ app.py
	ruff format --check geneai/ tests/ app.py

format:
	ruff format geneai/ tests/ app.py
	ruff check --fix geneai/ tests/ app.py

typecheck:
	mypy geneai/ --ignore-missing-imports --no-error-summary

check: lint typecheck test-smoke

# Docker
build:
	docker build -t geneai-research:latest .

build-staging:
	docker build -t geneai-research:staging -f Dockerfile .

build-prod:
	docker build -t geneai-research:production -f Dockerfile .

up:
	docker compose up -d

up-staging:
	docker compose -f docker-compose.staging.yml up -d

up-prod:
	docker compose -f docker-compose.production.yml up -d

down:
	docker compose down

down-staging:
	docker compose -f docker-compose.staging.yml down

down-prod:
	docker compose -f docker-compose.production.yml down

logs:
	docker compose logs -f

logs-staging:
	docker compose -f docker-compose.staging.yml logs -f

logs-prod:
	docker compose -f docker-compose.production.yml logs -f

ps:
	docker compose ps

# Deployment
deploy-staging:
	./scripts/deploy.sh -e staging

deploy-prod:
	./scripts/deploy.sh -e production

rollback-staging:
	./scripts/deploy.sh -e staging -a rollback

rollback-prod:
	./scripts/deploy.sh -e production -a rollback

backup-staging:
	./scripts/deploy.sh -e staging -a backup

backup-prod:
	./scripts/deploy.sh -e production -a backup

# Database
db-shell:
	docker compose exec postgres psql -U geneai -d geneai

db-backup:
	mkdir -p backups
	docker compose exec -T postgres pg_dump -U geneai geneai > backups/geneai_$(shell date +%Y%m%d_%H%M%S).sql

db-restore:
	@echo "Usage: make db-restore BACKUP=backups/geneai_20240101_120000.sql"
	@if [ -n "$(BACKUP)" ]; then \
		docker compose exec -T postgres psql -U geneai -d geneai < $(BACKUP); \
	fi

# Cleanup
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov .coverage coverage.xml bandit-report.json safety-report.json

clean-all: clean
	docker compose down -v
	docker compose -f docker-compose.staging.yml down -v
	docker compose -f docker-compose.production.yml down -v
	docker system prune -f

# Development helpers
shell:
	docker compose exec app bash

shell-staging:
	docker compose -f docker-compose.staging.yml exec app bash

shell-prod:
	docker compose -f docker-compose.production.yml exec app bash

# Generate requirements from current environment
freeze:
	pip freeze > requirements-lock.txt

# Update dependencies
update-deps:
	pip install --upgrade pip
	pip install -U -r requirements.txt
	pip freeze > requirements-lock.txt

# Security audit
security-audit:
	bandit -r geneai/
	safety check

# Generate documentation
docs:
	@echo "Documentation generation not yet implemented"