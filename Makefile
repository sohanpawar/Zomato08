.PHONY: help install install-dev lint format type-check test test-cov run-api run-ui run-ingestion docker-build-backend docker-build-frontend deploy-check clean

PYTHON := python3

help:
	@echo "AI-Powered Restaurant Recommendation System Commands:"
	@echo "  make install                Install runtime dependencies"
	@echo "  make install-dev            Install development & test dependencies"
	@echo "  make lint                   Run Ruff linter"
	@echo "  make format                 Format code with Black and Ruff"
	@echo "  make type-check             Run mypy type checker"
	@echo "  make test                   Run pytest suite"
	@echo "  make test-cov               Run pytest with coverage report"
	@echo "  make run-api                Start FastAPI server with uvicorn"
	@echo "  make run-ui                 Start Streamlit frontend"
	@echo "  make run-ingestion          Run dataset ingestion pipeline"
	@echo "  make docker-build-backend   Build production Docker container for FastAPI backend"
	@echo "  make docker-build-frontend  Build production Docker container for Streamlit UI"
	@echo "  make deploy-check           Verify deployment files and configurations"
	@echo "  make clean                  Remove caches and build artifacts"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

lint:
	ruff check src tests scripts

format:
	black src tests scripts
	ruff check --fix src tests scripts

type-check:
	mypy src tests scripts

test:
	PYTHONPATH=src pytest tests/unit

test-cov:
	PYTHONPATH=src pytest --cov=src/app --cov-report=term-missing tests/

run-api:
	PYTHONPATH=src uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

run-ui:
	PYTHONPATH=src streamlit run ui/streamlit_app.py

run-ingestion:
	PYTHONPATH=src $(PYTHON) scripts/run_ingestion.py

docker-build-backend:
	docker build -f Dockerfile.backend -t nextleap-backend:latest .

docker-build-frontend:
	docker build -f Dockerfile.frontend -t nextleap-frontend:latest .

deploy-check:
	@echo "Checking deployment files..."
	@test -f Dockerfile.backend && echo "✓ Dockerfile.backend present" || echo "✗ Dockerfile.backend missing"
	@test -f Dockerfile.frontend && echo "✓ Dockerfile.frontend present" || echo "✗ Dockerfile.frontend missing"
	@test -f railway.json && echo "✓ railway.json present" || echo "✗ railway.json missing"
	@test -f vercel.json && echo "✓ vercel.json present" || echo "✗ vercel.json missing"
	@test -f Procfile && echo "✓ Procfile present" || echo "✗ Procfile missing"
	@test -f .dockerignore && echo "✓ .dockerignore present" || echo "✗ .dockerignore missing"
	@test -f .github/workflows/deploy.yml && echo "✓ GitHub Actions workflow present" || echo "✗ GitHub Actions workflow missing"
	@echo "Deployment configuration check completed."

clean:
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov build dist *.egg-info
