# BearCase AI task runner. `make setup` then `make dev`.
SHELL := /bin/bash
API := apps/api
WEB := apps/web
UV ?= uv

.PHONY: setup api web dev seed fixtures test test-api test-web lint typecheck eval e2e build ci clean docker-up docker-down

setup: ## Install Python and Node dependencies
	cd $(API) && $(UV) sync --all-extras
	cd $(WEB) && npm install --no-fund --no-audit --legacy-peer-deps
	@test -f .env || cp .env.example .env

api: ## Run the API (auto-migrates on start)
	cd $(API) && $(UV) run bearcase serve --reload

web: ## Run the Next.js app
	cd $(WEB) && npm run dev

dev: ## Run API and web together
	$(MAKE) -j2 api web

seed: ## Seed the fictional Northstar HVAC deal
	cd $(API) && $(UV) run bearcase seed

fixtures: ## Regenerate the Northstar fixture files
	cd $(API) && $(UV) run bearcase generate-fixtures

test-api:
	cd $(API) && $(UV) run pytest -q

test-web:
	cd $(WEB) && npm run test

test: test-api test-web ## Run unit and integration tests

lint:
	cd $(API) && $(UV) run ruff check . && $(UV) run ruff format --check .
	cd $(WEB) && npm run lint

typecheck:
	cd $(API) && $(UV) run mypy src
	cd $(WEB) && npx tsc --noEmit

eval: ## Run the AI evaluation suite against ground truth
	cd $(API) && $(UV) run bearcase eval

e2e: ## Playwright smoke tests
	cd $(WEB) && npx playwright test

build:
	cd $(WEB) && npm run build

ci: lint typecheck test eval build ## Everything CI runs

docker-up:
	docker compose -f infra/docker-compose.yml up --build

docker-down:
	docker compose -f infra/docker-compose.yml down -v

clean: ## Remove the local database, storage, and build output
	$(RM) -r data $(WEB)/.next $(API)/.pytest_cache
