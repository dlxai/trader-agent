# JMWL Trading Backend - Makefile

.PHONY: help install dev test lint format migrate seed clean docker-build docker-run

# Default target
help:
	@echo "JMWL Trading Backend - Available Commands:"
	@echo ""
	@echo "  make install      - Install dependencies with Poetry"
	@echo "  make dev          - Run development server with hot reload"
	@echo "  make test         - Run test suite"
	@echo "  make test-cov     - Run tests with coverage report"
	@echo "  make lint         - Run all linters (black, isort, ruff, mypy)"
	@echo "  make format       - Auto-format code with black and isort"
	@echo "  make migrate      - Run database migrations (upgrade to latest)"
	@echo "  make migrate-gen  - Generate new migration (requires MESSAGE var)"
	@echo "  make seed         - Seed database with initial data"
	@echo "  make clean        - Clean cache files and directories"
	@echo "  make docker-build - Build Docker image"
	@echo "  make docker-run   - Run Docker container"
	@echo ""

# Installation
install:
	poetry install

# Development server
dev:
	poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 3001

# Testing
test:
	poetry run pytest tests/ -v

test-cov:
	poetry run pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html

# Linting and formatting
lint:
	poetry run black --check src tests
	poetry run isort --check-only src tests
	poetry run ruff check src tests
	poetry run mypy src

format:
	poetry run black src tests
	poetry run isort src tests
	poetry run ruff check --fix src tests

# Database migrations
migrate:
	poetry run alembic upgrade head

migrate-gen:
	@if [ -z "$(MESSAGE)" ]; then \
		echo "Error: MESSAGE is required. Usage: make migrate-gen MESSAGE='your message'"; \
		exit 1; \
	fi
	poetry run alembic revision --autogenerate -m "$(MESSAGE)"

migrate-down:
	poetry run alembic downgrade -1

# Database seeding
seed:
	poetry run python scripts/seed_data.py

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	rm -f .coverage 2>/dev/null || true

# Docker commands
docker-build:
	docker build -t jmwl-backend:latest .

docker-run:
	docker run -p 3001:3001 --env-file .env jmwl-backend:latest

docker-compose-up:
	docker-compose up -d

docker-compose-down:
	docker-compose down
