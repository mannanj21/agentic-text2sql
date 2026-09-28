# ============================================================
# Agentic Text-to-SQL Analytics Platform — Makefile
# ============================================================
# On Windows without make, use: python scripts/make.py <target>
# ============================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help
BACKEND := backend
VENV := $(BACKEND)/.venv
UV := uv

.PHONY: help setup check lint fmt test-unit test-agent test-integration test-all smoke up down logs migrate seed eval fe-check e2e

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install all dependencies
	cd $(BACKEND) && $(UV) sync --all-extras
	@echo "✅ Backend dependencies installed"

check: lint test-unit ## Quick gate: lint + format check + types + unit tests

lint: ## Run ruff lint + format check + mypy
	cd $(BACKEND) && $(UV) run ruff check app tests
	cd $(BACKEND) && $(UV) run ruff format --check app tests
	cd $(BACKEND) && $(UV) run mypy app

fmt: ## Auto-format code
	cd $(BACKEND) && $(UV) run ruff check --fix app tests
	cd $(BACKEND) && $(UV) run ruff format app tests

test-unit: ## Run unit tests only
	cd $(BACKEND) && $(UV) run pytest tests/unit -x -q --tb=short

test-agent: ## Run agent tests (FakeLLM)
	cd $(BACKEND) && $(UV) run pytest tests/agent -x -q --tb=short

test-integration: ## Run integration tests (requires Postgres)
	cd $(BACKEND) && $(UV) run pytest tests/integration -x -q --tb=short -m integration

test-all: check test-agent test-integration ## Full gate: Quick + agent + integration

smoke: ## Stack smoke test (Docker Compose)
	bash scripts/smoke.sh

up: ## Start Docker Compose stack
	docker compose up -d --build --wait

down: ## Stop Docker Compose stack
	docker compose down

logs: ## Tail Docker Compose logs
	docker compose logs -f --tail=50

migrate: ## Run Alembic migrations
	cd $(BACKEND) && $(UV) run alembic upgrade head

seed: ## Seed demo databases
	docker compose exec demo-ecommerce psql -U demo -d ecommerce -f /docker-entrypoint-initdb.d/seed.sql
	docker compose exec demo-pagila psql -U demo -d pagila -f /docker-entrypoint-initdb.d/seed.sql

eval: ## Run evaluation on dev split
	cd $(BACKEND) && $(UV) run python -m evaluation.run --split dev

fe-check: ## Frontend: lint + typecheck + unit tests + build
	cd frontend && npm run lint && npm run typecheck && npm run test && npm run build

e2e: ## Run Playwright end-to-end tests
	cd frontend && npx playwright test
