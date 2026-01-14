.PHONY: help install lint format type-check build run-docker

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies with Poetry
	poetry install

lint: ## Run linting with Ruff
	poetry run ruff check .

format: ## Format code with Ruff (Black-compatible)
	poetry run ruff format .

type-check: ## Run type checking with mypy
	poetry run mypy confighole/

fix: format ## Fix code formatting and linting issues
	poetry run ruff check --fix .

check: fix format lint type-check ## Run all checks

build: ## Build Docker image
	docker build -t confighole .

run-docker: ## Run with docker-compose (shows help by default)
	docker-compose run --rm confighole

# Test commands
test: ## Run all tests
	poetry run pytest -v

test-unit: ## Run unit tests only
	poetry run pytest -m "unit"  -v

test-integration: ## Run integration tests only
	poetry run pytest -m "integration" -v

test-coverage: ## Run tests with coverage report
	poetry run pytest -v --cov=confighole --cov-report=term

test-docker: ## Start test Pi-hole container
	docker-compose -f tests/assets/pihole-docker-compose.yml up -d

test-docker-down: ## Stop test Pi-hole container
	docker-compose -f tests/assets/pihole-docker-compose.yml down -v

test-docker-clean: ## Stop and remove test Pi-hole container with volumes
	docker-compose -f tests/assets/pihole-docker-compose.yml down -v --remove-orphans

# Development commands
dev-install: install ## Install with development dependencies
	poetry install --with dev