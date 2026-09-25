# NextLeap AI Restaurant Recommendation System — Production Deployment Plan

> **Comprehensive End-to-End Deployment Guide for FastAPI Backend & Obsidian Streamlit / Web Frontend on Railway and Vercel.**

---

## 1. Executive Summary & Architecture Overview

This deployment plan outlines the step-by-step strategy for deploying the **AI-Powered Restaurant Recommendation System** (Zomato use case) into production. The system consists of:

1. **FastAPI Backend (API + Retrieval + LLM Engine)**:
   - High-performance asynchronous REST API (`src/app/main.py`).
   - Grounded candidate retrieval with progressive constraint relaxation (`src/app/integration/filters.py`).
   - SQLite indexed catalog + Parquet analytical store (`data/processed/restaurants.db`).
   - Groq Cloud LLM integration (`openai/gpt-oss-120b`) with in-memory TTL response caching (`RecommendationCache`) and strict rate limiting (`LLMRateLimiter`: 30 RPM, 8K TPM).
2. **Obsidian Culinary AI Frontend (Streamlit / Web UI)**:
   - Modern, modular component-based dark UI (`ui/streamlit_app.py`, `ui/components/`, `ui/theme.py`).
   - Real-time telemetry, discovery presets, interactive filter panels, and grounded AI reasoning cards.
   - Communicates with FastAPI via `ui/api_client.py`.

---

### 1.1 Target Cloud Topology

```
                                 ┌────────────────────────────────────────────────────────┐
                                 │                   PUBLIC INTERNET                      │
                                 └───────────────────────────┬────────────────────────────┘
                                                             │
                              ┌──────────────────────────────┴─────────────────────────────┐
                              │                                                            │
                              ▼                                                            ▼
            ┌───────────────────────────────────┐                        ┌───────────────────────────────────┐
            │        VERCEL (Edge / CDN)        │                        │        RAILWAY (Container / PaaS) │
            │   https://app.yourdomain.com      │                        │   https://api.yourdomain.com      │
            ├───────────────────────────────────┤                        ├───────────────────────────────────┤
            │ • Edge Caching & Static Assets    │                        │ • FastAPI Backend (Uvicorn ASGI)  │
            │ • Vercel API Gateway / Next.js UI │                        │ • SQLite Indexed Database         │
            │ • Reverse Proxy / Rewrites        │                        │ • Groq LLM Reasoning Engine      │
            │ • Custom Domain SSL Termination   │                        │ • In-Memory TTL Response Cache    │
            └─────────────────┬─────────────────┘                        └─────────────────▲─────────────────┘
                              │                                                            │
                              │             Secure HTTPS REST Calls                        │
                              └────────────────────────────────────────────────────────────┘
                                                            │
                                                            ▼
                                         ┌───────────────────────────────────┐
                                         │       GROQ CLOUD INFERENCE        │
                                         │   Model: openai/gpt-oss-120b      │
                                         │   Base: https://api.groq.com/v1   │
                                         └───────────────────────────────────┘
```

---

### 1.2 Platform Fit Analysis

| Platform | Best Role | Strengths | Considerations |
| :--- | :--- | :--- | :--- |
| **Railway** | **Primary Backend & Streamlit Host** | • Native persistent services with zero cold starts<br>• Dynamic `$PORT` binding<br>• Persistent volumes for SQLite database<br>• Built-in private networking between services<br>• Native Docker & Nixpacks support | • Usage-based compute billing ($5/mo tier or pay-as-you-go) |
| **Vercel** | **Edge CDN & Web Frontend / API Proxy** | • Instant global CDN and edge routing<br>• Automatic SSL and custom domain management<br>• Preview deployments per Git branch<br>• Seamless serverless scaling | • Streamlit's WebSocket architecture is not natively suited for stateless serverless functions; best used with a Next.js/React frontend or as a secure API reverse proxy |

---

## 2. Deployment Strategies

We provide two production-ready deployment strategies depending on your operational preferences:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ STRATEGY 1 (RECOMMENDED): Dual-Service Railway Deployment                                       │
│ • Service 1 (Backend): FastAPI + SQLite + Groq Engine                                           │
│ • Service 2 (Frontend): Streamlit UI (Obsidian Theme)                                           │
│ ➔ Simplest setup, full WebSocket support, single project dashboard, zero CORS issues.          │
├─────────────────────────────────────────────────────────────────────────────────────────────────┤
│ STRATEGY 2 (HYBRID): Railway Backend + Vercel Frontend / API Proxy                              │
│ • Railway: FastAPI Backend API + Data Layer                                                     │
│ • Vercel: Edge Gateway / Next.js Frontend with reverse proxy rewrites to Railway                │
│ ➔ Maximum frontend performance, global CDN distribution, edge SSL caching.                      │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Step-by-Step Deployment: Strategy 1 (Railway Full Stack)

### Step 1: Pre-Deployment Repository Preparation

1. **Initialize Git Repository** (if not already done):
   ```bash
   cd /Users/sohan/Desktop/NextLeap
   git init
   git add .
   git commit -m "feat: complete AI recommendation engine and Obsidian UI"
   ```

2. **Push to GitHub**:
   ```bash
   # Create a repository on GitHub (via gh CLI or web UI)
   gh repo create nextleap-restaurant-recommender --public --source=. --remote=origin --push
   # Or standard git push
   git remote add origin https://github.com/<your-username>/nextleap-restaurant-recommender.git
   git branch -M main
   git push -u origin main
   ```

3. **Verify Pre-Ingested Dataset**:
   Ensure `data/processed/restaurants.db` is tracked or generated during container build. For container builds, the Dockerfile runs `scripts/run_ingestion.py` automatically if the database does not exist.

---

### Step 2: Deploy FastAPI Backend on Railway

1. **Sign in to Railway**:
   - Go to [railway.app](https://railway.app/) and authenticate with GitHub.

2. **Create New Project**:
   - Click **"New Project"** → Select **"Deploy from GitHub repo"**.
   - Select `nextleap-restaurant-recommender`.

3. **Configure Backend Service**:
   - In Service Settings, name the service: `nextleap-backend`.
   - **Root Directory**: `/` (repository root).
   - **Build Command** (if using Nixpacks):
     ```bash
     pip install -r requirements.txt && PYTHONPATH=src python scripts/run_ingestion.py --file tests/fixtures/sample_raw_hf_zomato.json --force
     ```
   - **Start Command**:
     ```bash
     PYTHONPATH=src uvicorn app.main:app --host 0.0.0.0 --port $PORT
     ```

4. **Set Backend Environment Variables**:
   In the **Variables** tab of `nextleap-backend`, configure:

   | Variable | Value | Description |
   | :--- | :--- | :--- |
   | `APP_ENV` | `production` | Enables production optimizations |
   | `DEBUG` | `false` | Disables debug traces in API responses |
   | `LOG_LEVEL` | `INFO` | Standard production logging |
   | `JSON_LOGS` | `true` | Structured JSON log outputs for log aggregators |
   | `LLM_PROVIDER` | `groq` | Active LLM inference provider |
   | `LLM_MODEL` | `openai/gpt-oss-120b` | Production Groq model |
   | `GROQ_API_KEY` | `gsk_...` *(Your Secret Key)* | Groq API Key |
   | `LLM_API_KEY` | `gsk_...` *(Your Secret Key)* | Fallback LLM Key |
   | `SHORTLIST_SIZE` | `12` | K candidates injected into LLM prompt |
   | `DEFAULT_TOP_N` | `5` | Recommendations count |
   | `RATE_LIMIT_RPM` | `30` | RPM quota protection |
   | `RATE_LIMIT_TPM` | `8000` | TPM token quota protection |
   | `CORS_ORIGINS` | `["*"]` *(or your frontend URL)* | Allowed CORS origins |
   | `SQLITE_PATH` | `data/processed/restaurants.db` | Local SQLite path |

5. **Generate Public Domain**:
   - In **Settings** → **Networking** → Click **"Generate Domain"** (e.g., `nextleap-backend-production.up.railway.app`).

6. **Verify Backend Health**:
   ```bash
   curl -s https://<your-backend-domain>.up.railway.app/health | jq
   ```
   *Expected Response:*
   ```json
   {
     "status": "healthy",
     "database_available": true,
     "total_restaurants": 411,
     "version": "0.1.0"
   }
   ```

---

### Step 3: Deploy Streamlit Frontend on Railway

1. **Add Frontend Service to the Same Railway Project**:
   - In the same Railway project canvas, click **"+ New"** → **"GitHub Repo"** → Select the same repository.
   - Rename this second service to `nextleap-frontend`.

2. **Configure Frontend Service Settings**:
   - **Start Command**:
     ```bash
     PYTHONPATH=src streamlit run ui/streamlit_app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true
     ```

3. **Set Frontend Environment Variables**:
   In the **Variables** tab of `nextleap-frontend`:

   | Variable | Value | Description |
   | :--- | :--- | :--- |
   | `BACKEND_API_URL` | `https://<your-backend-domain>.up.railway.app` | Public URL of the FastAPI backend |
   | `STREAMLIT_SERVER_PORT` | `$PORT` | Dynamic Railway port binding |
   | `STREAMLIT_SERVER_HEADLESS` | `true` | Runs without opening local browser |
   | `STREAMLIT_BROWSER_GATHER_USAGE_STATS` | `false` | Disables telemetry prompts |

4. **Generate Public Frontend Domain**:
   - In **Settings** → **Networking** → Click **"Generate Domain"** (e.g., `nextleap-ui-production.up.railway.app`).

5. **Update Backend CORS Configuration**:
   - Go back to `nextleap-backend` variables.
   - Update `CORS_ORIGINS`:
     ```json
     ["https://nextleap-ui-production.up.railway.app", "http://localhost:8502"]
     ```

---

## 4. Step-by-Step Deployment: Strategy 2 (Railway Backend + Vercel Frontend / Proxy)

If you are hosting a Next.js / React / Static SPA on Vercel or using Vercel as an Edge API Gateway with custom domains:

### Step 1: Deploy Backend on Railway (as detailed in §3 Step 2)
Your backend will be accessible at `https://nextleap-backend-production.up.railway.app`.

---

### Step 2: Configure Vercel Project

1. **Create `vercel.json`** in project root:
   ```json
   {
     "version": 2,
     "rewrites": [
       {
         "source": "/api/v1/:path*",
         "destination": "https://nextleap-backend-production.up.railway.app/:path*"
       },
       {
         "source": "/health",
         "destination": "https://nextleap-backend-production.up.railway.app/health"
       },
       {
         "source": "/meta",
         "destination": "https://nextleap-backend-production.up.railway.app/meta"
       },
       {
         "source": "/recommend",
         "destination": "https://nextleap-backend-production.up.railway.app/recommend"
       }
     ],
     "headers": [
       {
         "source": "/(.*)",
         "headers": [
           { "key": "X-Content-Type-Options", "value": "nosniff" },
           { "key": "X-Frame-Options", "value": "DENY" },
           { "key": "X-XSS-Protection", "value": "1; mode=block" }
         ]
       }
     ]
   }
   ```

2. **Deploy to Vercel via CLI**:
   ```bash
   # Install Vercel CLI
   npm i -g vercel

   # Link project and deploy
   vercel --prod
   ```

3. **Or Deploy via Vercel Web Dashboard**:
   - Go to [vercel.com](https://vercel.com) → **"Add New Project"** → Import GitHub repo.
   - Set Environment Variables:
     - `BACKEND_API_URL`: `https://nextleap-backend-production.up.railway.app`
   - Click **Deploy**.

---

## 5. Production Docker Configurations

To ensure 100% environment reproducibility, container manifests are provided for both services.

### 5.1 Backend Dockerfile (`Dockerfile.backend`)

```dockerfile
# Multi-stage lightweight Python 3.11 image for FastAPI backend
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final runtime image
FROM python:3.11-slim AS runner

WORKDIR /app

# Security: Create non-root user
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --gid 1001 appuser

# Copy installed dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONPATH=/app/src:/app

# Copy application code and fixtures
COPY src/ /app/src/
COPY scripts/ /app/scripts/
COPY tests/fixtures/ /app/tests/fixtures/
COPY pyproject.toml /app/

# Create data directories with appropriate permissions
RUN mkdir -p /app/data/processed /app/data/raw && \
    chown -R appuser:appgroup /app

USER appuser

# Pre-seed dataset if DB is not mounted
RUN python scripts/run_ingestion.py --file tests/fixtures/sample_raw_hf_zomato.json --force || true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

---

### 5.2 Frontend Dockerfile (`Dockerfile.frontend`)

```dockerfile
# Lightweight Python 3.11 image for Streamlit Frontend
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application, UI components and styles
COPY src/ /app/src/
COPY ui/ /app/ui/
COPY .streamlit/ /app/.streamlit/

ENV PYTHONPATH=/app/src:/app
ENV STREAMLIT_SERVER_PORT=8502
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8502

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8502/_stcore/health || exit 1

CMD ["sh", "-c", "streamlit run ui/streamlit_app.py --server.port ${PORT:-8502} --server.address 0.0.0.0 --server.headless true"]
```

---

### 5.3 `.dockerignore`

```
.git
.github
__pycache__
*.pyc
*.pyo
*.pyd
.Python
.pytest_cache
.mypy_cache
.ruff_cache
.coverage
htmlcov
.venv
venv
env
.DS_Store
*.log
terminals/
```

---

### 5.4 Declarative Railway Configuration (`railway.json`)

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS",
    "nixpacksPlan": {
      "phases": {
        "setup": {
          "nixPkgs": ["python311", "sqlite"]
        },
        "install": {
          "cmds": ["pip install -r requirements.txt"]
        }
      }
    }
  },
  "deploy": {
    "startCommand": "PYTHONPATH=src uvicorn app.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 15,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 5
  }
}
```

---

## 6. Complete Environment Variable Reference Matrix

| Variable Name | Required | Default (Dev) | Recommended (Prod) | Purpose |
| :--- | :---: | :--- | :--- | :--- |
| `APP_ENV` | Yes | `development` | `production` | Enables production security & logging modes |
| `DEBUG` | No | `true` | `false` | Hides internal stack traces in 500 error responses |
| `LOG_LEVEL` | No | `INFO` | `INFO` | Controls logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `JSON_LOGS` | No | `false` | `true` | Emits structured JSON log lines for Datadog / Railway / CloudWatch |
| `API_HOST` | No | `0.0.0.0` | `0.0.0.0` | Binding host address |
| `API_PORT` / `PORT` | Yes | `8000` | Dynamic `$PORT` | Port injected by Railway |
| `CORS_ORIGINS` | Yes | `["*"]` | `["https://app.yourdomain.com"]` | Restricts API access to authorized frontend origins |
| `BACKEND_API_URL` | Yes | `http://localhost:8000` | `https://api.yourdomain.com` | Base URL used by UI to invoke backend endpoints |
| `LLM_PROVIDER` | Yes | `groq` | `groq` | Inference backend (`groq`, `openai`, `gemini`, `mock`) |
| `LLM_MODEL` | Yes | `openai/gpt-oss-120b` | `openai/gpt-oss-120b` | Model slug for structured recommendation generation |
| `GROQ_API_KEY` | **Yes** | *None* | `gsk_...` | Groq API authentication credential |
| `LLM_TEMPERATURE` | No | `0.2` | `0.2` | Keeps AI reasoning grounded and reproducible |
| `LLM_MAX_TOKENS` | No | `600` | `600` | Max tokens per response (conserves Groq TPM quota) |
| `LLM_TIMEOUT_SECONDS` | No | `10.0` | `8.0` | Max wait time before triggering heuristic fallback |
| `LLM_MAX_RETRIES` | No | `2` | `2` | Exponential backoff retry attempts on 429/5xx |
| `RATE_LIMIT_RPM` | No | `30` | `30` | Requests-per-minute quota rate limiter |
| `RATE_LIMIT_TPM` | No | `8000` | `8000` | Tokens-per-minute quota rate limiter |
| `SQLITE_PATH` | No | `data/processed/restaurants.db` | `data/processed/restaurants.db` | Path to SQLite database file |
| `SHORTLIST_SIZE` | No | `12` | `12` | K candidate restaurants passed into LLM prompt |
| `DEFAULT_TOP_N` | No | `5` | `5` | Default number of final recommendations |

---

## 7. Automated CI/CD Pipeline (GitHub Actions)

Create `.github/workflows/deploy.yml` for automated linting, unit testing, and continuous deployment:

```yaml
name: CI/CD Pipeline — Test & Deploy

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    name: Lint & Test Suite
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install ruff pytest pytest-asyncio pytest-cov

      - name: Code Quality & Lint Checks
        run: |
          ruff check src tests scripts

      - name: Run Test Suite
        env:
          APP_ENV: test
          LLM_PROVIDER: mock
        run: |
          PYTHONPATH=src pytest tests/unit -v --cov=src/app

  deploy-railway:
    name: Trigger Railway Deployment
    needs: test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Install Railway CLI
        run: npm i -g @railway/cli

      - name: Deploy to Railway
        env:
          RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}
        run: |
          railway up --service nextleap-backend --detach
          railway up --service nextleap-frontend --detach
```

---

## 8. Database Management & Concurrency in Production

1. **WAL Mode (Write-Ahead Logging)**:
   The SQLite connection pool is configured with `PRAGMA journal_mode=WAL;` and `timeout=30.0` in `src/app/data/repository.py` to support high-concurrency read operations.

2. **Database Ingestion on Boot**:
   If the database is not pre-populated, the container automatically populates it using `scripts/run_ingestion.py`:
   ```bash
   PYTHONPATH=src python scripts/run_ingestion.py --limit 500 --force
   ```

3. **Persistent Volume on Railway (Optional)**:
   If you plan to ingest datasets dynamically at runtime, add a **Railway Volume**:
   - Mount Path: `/app/data/processed`
   - Size: 1 GB (plenty for 50k+ restaurants).

---

## 9. Security & Production Hardening Checklist

- [x] **Zero Secrets in Git**: Verified `.gitignore` prevents `.env`, `*.key`, `*.pem`, and credentials from being committed.
- [x] **CORS Origin Whitelisting**: Restricted to exact frontend production domain.
- [x] **Non-Root Container User**: Configured `appuser` (UID 1001) in Dockerfile.
- [x] **LLM Anti-Hallucination & Fallback**: If Groq API experiences rate limits or network drops, the backend automatically falls back to deterministic heuristic recommendations without crashing.
- [x] **Rate Limit Guard**: In-memory token bucket prevents 429 quota exhaustion on Groq API.
- [x] **HTML Output Sanitization**: Dynamic LLM text is sanitized via `html.escape` in `ui/html_renderer.py`.
- [x] **Health Check & Latency Headers**: `/health` endpoint and `X-Response-Time-Ms` middleware enabled on all API responses.

---

## 10. Troubleshooting & Rollback Runbook

### Issue 1: Backend returns `502 Bad Gateway` on Railway
- **Cause**: Uvicorn not binding to Railway's dynamic `$PORT`.
- **Fix**: Ensure start command uses `--port $PORT`:
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port $PORT
  ```

### Issue 2: Frontend displays `Could not connect to backend server`
- **Cause**: `BACKEND_API_URL` environment variable is missing or contains a trailing slash/invalid protocol.
- **Fix**: Check `BACKEND_API_URL` in Railway/Vercel settings. It must be `https://<your-backend-subdomain>.up.railway.app` without a trailing slash.

### Issue 3: Groq Rate Limit (`LLMProviderError: Rate limit exceeded`)
- **Cause**: Groq TPM/RPM limits reached on free tier.
- **Fix**: The system automatically switches to deterministic fallback mode. To increase limits, upgrade Groq Cloud tier or adjust `SHORTLIST_SIZE=8` and `LLM_MAX_TOKENS=400` in environment variables.

### Issue 4: Rollback Procedure
- **Railway**: Go to **Deployments** tab → Click **"..."** on previous successful build → Select **"Rollback to this deployment"**.
- **Vercel**: Go to **Deployments** tab → Click **"Instant Rollback"** to previous production release.

---

## 11. Quick Deployment Command Summary

```bash
# 1. Install Railway CLI
npm i -g @railway/cli

# 2. Authenticate
railway login

# 3. Link project
railway link

# 4. Deploy Backend
railway up --service nextleap-backend

# 5. Deploy Frontend
railway up --service nextleap-frontend

# 6. Verify Health
curl -s https://<your-backend-url>/health
```
