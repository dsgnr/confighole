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

format: ## Format code with Ruff
	poetry run ruff format .

type-check: ## Run type checking with mypy
	poetry run mypy confighole/

fix: format ## Fix code formatting and linting issues
	poetry run ruff check --fix .

check: lint type-check ## Run all checks

build: ## Build Docker image
	docker build -t confighole .

run-docker: ## Run with docker-compose (shows help by default)
	docker-compose run --rm confighole

# Development commands
dev-install: install ## Install with development dependencies
	poetry install --with dev