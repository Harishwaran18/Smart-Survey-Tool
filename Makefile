.DEFAULT_GOAL := help
.RECIPEPREFIX := >
PYTHON ?= python
PORT_API ?= 8000
PORT_UI ?= 8501

.PHONY: help install dev-install run api ui seed test lint format typecheck cov docker-build docker-up clean

help: ## Show available commands
> @grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install runtime dependencies
> $(PYTHON) -m pip install -r requirements.txt

dev-install: ## Install runtime + development dependencies
> $(PYTHON) -m pip install -r requirements-dev.txt
> $(PYTHON) -m pip install -e .

run: ui ## Alias for `make ui`

api: ## Run the REST API with autoreload
> $(PYTHON) -m uvicorn smart_survey.api.main:app --reload --port $(PORT_API)

ui: ## Run the Streamlit dashboard
> $(PYTHON) -m streamlit run app.py --server.port $(PORT_UI)

seed: ## Create demo survey data
> $(PYTHON) -m smart_survey seed --responses 60 --force

test: ## Run the test suite
> $(PYTHON) -m pytest

cov: ## Run tests with coverage report
> $(PYTHON) -m pytest --cov=smart_survey --cov-report=term-missing

lint: ## Lint with ruff
> $(PYTHON) -m ruff check .

format: ## Format with ruff
> $(PYTHON) -m ruff format .

typecheck: ## Static type check with mypy
> $(PYTHON) -m mypy smart_survey

docker-build: ## Build the Docker image
> docker build -t smart-survey-tool:latest .

docker-up: ## Start API and UI with Docker Compose
> docker compose up --build

clean: ## Remove caches and build artefacts
> rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage build dist *.egg-info
> find . -type d -name __pycache__ -prune -exec rm -rf {} +
