# Architecture — AI-Powered Restaurant Recommendation System

> Reference: see [`problemStatement.md`](./problemStatement.md) for the functional goals this architecture implements.

This document describes the end-to-end architecture for an AI-powered restaurant recommendation service (Zomato use case). It combines a **structured data layer** (the Zomato dataset) with a **Large Language Model** to produce ranked, explained, human-like recommendations from user preferences.

---

## 1. Goals & Non-Goals

### Goals
- Ingest and preprocess the Zomato dataset once, then serve fast queries.
- Accept structured user preferences (location, budget, cuisine, min rating, extras).
- Deterministically **filter** candidates from the dataset, then use an **LLM to rank + explain**.
- Return a clean, user-friendly list of top recommendations with AI-generated reasoning.
- Keep the LLM prompt grounded in real data to minimize hallucination.

### Non-Goals (v1)
- No user accounts, auth, or persisted user history.
- No live/real-time restaurant data (uses a static dataset snapshot).
- No online ordering, payments, or map integration.
- No fine-tuning of the LLM (prompt-engineering only).

---

## 2. High-Level Architecture

```
┌──────────────┐        ┌───────────────────────────────────────────────┐
│              │        │                  Backend (FastAPI)             │
│   Frontend   │  HTTP  │                                               │
│  (Streamlit/ │ ─────► │  ┌──────────┐  ┌───────────┐  ┌────────────┐ │
│   React UI)  │  JSON  │  │  API     │─►│Integration│─►│Recommend-  │ │
│              │ ◄───── │  │  Layer   │  │  Layer    │  │ation Engine│ │
└──────────────┘        │  └──────────┘  └─────┬─────┘  └─────┬──────┘ │
                        │                      │              │        │
                        │                ┌─────▼─────┐   ┌────▼─────┐  │
                        │                │ Data Store│   │   LLM    │  │
                        │                │(Parquet/  │   │ Provider │  │
                        │                │  SQLite)  │   │ (OpenAI/ │  │
                        │                └─────▲─────┘   │  local)  │  │
                        └──────────────────────┼─────────┴──────────┘  │
                                               │
                                     ┌─────────┴──────────┐
                                     │  Ingestion Pipeline│
                                     │ (HuggingFace load, │
                                     │  clean, normalize) │
                                     └────────────────────┘
```

**Flow:** User preferences → API → deterministic filtering over structured data → prompt construction → LLM ranking/explanation → formatted response → UI.

---

## 3. Component Breakdown

### 3.1 Data Ingestion Pipeline
Responsible for turning the raw Hugging Face dataset into a clean, query-ready store. Runs offline (a one-time / scheduled script), not on the request path.

- **Source:** [`ManikaSaini/zomato-restaurant-recommendation`](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation) via the `datasets` library.
- **Steps:**
  1. Load the dataset (`load_dataset(...)`).
  2. Select relevant fields: `name`, `location`/`city`, `cuisines`, `cost` (cost for two), `rating`, plus extras (e.g., `online_delivery`, `table_booking`).
  3. Clean & normalize:
     - Parse cost to numeric (strip currency symbols/commas).
     - Normalize ratings to a float scale (e.g., 0–5); drop `"NEW"`/`"-"` values.
     - Lowercase & trim cuisine/location strings; split multi-cuisine strings into lists.
     - De-duplicate restaurants; drop rows missing critical fields.
  4. Derive a **budget bucket** per restaurant (`low`/`medium`/`high`) from cost percentiles.
  5. Persist to a fast local store (**Parquet** for analytics + **SQLite** for indexed filtering).
- **Output:** `data/processed/restaurants.parquet` and/or `data/processed/restaurants.db`.

### 3.2 Data Store
- **Primary:** SQLite (indexed on `city`, `budget_bucket`, `rating`) for fast filtering with zero external infra.
- **Alternative:** In-memory pandas DataFrame loaded from Parquet at startup for small datasets.
- Loaded once at application startup and cached.

### 3.3 API Layer (FastAPI)
- Validates and parses incoming requests with **Pydantic** models.
- Orchestrates: Integration Layer → Recommendation Engine → response formatting.
- Endpoints:
  - `GET  /health` — liveness check.
  - `GET  /meta` — available cities, cuisines, cost range (to populate UI dropdowns).
  - `POST /recommend` — main recommendation endpoint (see §5).

### 3.4 Integration Layer (Retrieval + Prompt Assembly)
The bridge between structured data and the LLM.

- **Filtering:** Apply hard constraints from user input:
  - `location == city`
  - `budget_bucket == budget`
  - cuisine overlap with requested cuisine(s)
  - `rating >= min_rating`
- **Pre-ranking / shortlisting:** Sort candidates (e.g., by rating desc, then value = rating/cost) and take **top-K** (e.g., K=15–25) to keep the prompt small and cheap.
- **Prompt assembly:** Serialize the shortlist into compact, structured context (JSON/markdown table) and inject user preferences + extras into a templated prompt (see §6).

### 3.5 Recommendation Engine (LLM)
- Sends the grounded prompt to the LLM provider.
- Asks the model to **rank** the shortlist, **explain** each pick, and optionally **summarize**.
- Enforces **structured JSON output** (function/tool calling or a strict response schema) so results are machine-parseable.
- Post-processes: validate the LLM only used restaurants from the shortlist (anti-hallucination guard), attach original structured fields back to each ranked item.

### 3.6 LLM Provider Abstraction
- A thin interface (`LLMClient.generate(prompt, schema)`) with pluggable backends:
  - **Hosted:** OpenAI / Anthropic / Gemini (configurable via env).
  - **Local:** Ollama (e.g., Llama 3.x) for offline/dev.
- Config-driven model name, temperature (low, e.g., 0.2 for consistency), max tokens, and timeout/retry.

### 3.7 Frontend
- **v1: Streamlit** — fastest path: preference form (dropdowns/sliders) + results cards. Ideal for a demo.
- **Alt: React + Vite** — if a richer, production-style UI is desired; talks to the same FastAPI endpoints.
- Displays each recommendation as a card: **Name, Cuisine, Rating, Estimated Cost, AI explanation**.

---

## 4. Data Model

### Restaurant (internal, post-ingestion)
| Field           | Type      | Notes                                   |
|-----------------|-----------|-----------------------------------------|
| `id`            | string    | Stable unique id                        |
| `name`          | string    | Restaurant name                         |
| `city`          | string    | Normalized location                     |
| `area`          | string    | Optional sub-locality                   |
| `cuisines`      | list[str] | Normalized, split                       |
| `cost_for_two`  | int       | Numeric, currency-stripped              |
| `budget_bucket` | enum      | `low` / `medium` / `high`               |
| `rating`        | float     | 0–5                                     |
| `votes`         | int       | Optional, for tie-breaking              |
| `features`      | list[str] | e.g., `family-friendly`, `quick-service`|

---

## 5. API Contract

### `POST /recommend`

**Request**
```json
{
  "location": "Bangalore",
  "budget": "medium",
  "cuisine": ["Italian", "Chinese"],
  "min_rating": 4.0,
  "preferences": ["family-friendly", "quick service"],
  "top_n": 5
}
```

**Response**
```json
{
  "query_echo": { "location": "Bangalore", "budget": "medium" },
  "count": 5,
  "recommendations": [
    {
      "rank": 1,
      "name": "Trattoria Uno",
      "cuisine": ["Italian"],
      "rating": 4.4,
      "estimated_cost": 1200,
      "explanation": "Great fit for a family dinner — high rating, mid-range cost, and known for quick service."
    }
  ],
  "summary": "Top Italian/Chinese picks in Bangalore under a medium budget, all rated 4.0+."
}
```

**Validation rules (Pydantic):** `budget ∈ {low, medium, high}`, `0 ≤ min_rating ≤ 5`, `1 ≤ top_n ≤ 20`, `location` required.

**Edge cases:** if filtering yields zero candidates, relax constraints progressively (drop cuisine → lower min_rating → widen budget) and flag the relaxation in `summary`.

---

## 6. Prompt Design

**System prompt (intent):** "You are a restaurant recommendation assistant. Rank ONLY the provided restaurants for the user's preferences. Never invent restaurants. Return valid JSON matching the schema."

**User prompt template:**
```
User preferences:
- Location: {location}
- Budget: {budget}
- Cuisine: {cuisine}
- Minimum rating: {min_rating}
- Extras: {preferences}

Candidate restaurants (choose and rank from THIS list only):
{shortlist_as_json}

Task:
1. Select and rank the top {top_n} restaurants that best match.
2. For each, give a 1–2 sentence explanation grounded in its fields.
3. Provide a short overall summary.
Return JSON: { "recommendations": [{ "name", "explanation" }...], "summary" }.
```

**Grounding guardrail:** the engine cross-checks returned names against the shortlist and discards any hallucinated entries before responding.

---

## 7. Technology Stack

| Layer            | Choice                          | Why                                       |
|------------------|---------------------------------|-------------------------------------------|
| Language         | Python 3.11+                    | Best ecosystem for data + LLM             |
| Data ingestion   | `datasets`, `pandas`            | Native HF loading + cleaning              |
| Storage          | Parquet + SQLite                | Zero-infra, fast filtering                |
| Backend          | FastAPI + Pydantic + Uvicorn    | Typed, async, auto OpenAPI docs           |
| LLM              | OpenAI/Anthropic/Gemini or Ollama | Pluggable hosted or local               |
| Frontend         | Streamlit (v1) / React (alt)    | Fast demo vs. production UI               |
| Config/secrets   | `pydantic-settings` + `.env`    | Clean env-based config                    |
| Testing          | `pytest`                        | Unit + integration tests                  |
| Tooling          | `ruff`, `black`, `mypy`         | Lint, format, type-check                  |
| Container        | Docker + docker-compose         | Reproducible deploys                      |

---

## 8. Proposed Project Structure

```
NextLeap/
├── docs/
│   ├── problemStatement.md
│   └── architecture.md
├── data/
│   ├── raw/                  # cached HF download
│   └── processed/            # restaurants.parquet / .db
├── src/
│   └── app/
│       ├── main.py           # FastAPI entrypoint
│       ├── config.py         # settings (env-driven)
│       ├── models/           # Pydantic schemas (request/response)
│       ├── ingestion/
│       │   └── pipeline.py   # load + clean + persist
│       ├── data/
│       │   └── repository.py # query/filter the store
│       ├── integration/
│       │   ├── filters.py    # hard-constraint filtering + shortlist
│       │   └── prompt.py     # prompt templating
│       ├── llm/
│       │   ├── client.py     # LLMClient interface
│       │   └── providers/    # openai.py, ollama.py, ...
│       └── engine/
│           └── recommender.py# orchestrates filter→prompt→LLM→parse
├── ui/
│   └── streamlit_app.py      # v1 frontend
├── tests/
├── scripts/
│   └── run_ingestion.py
├── .env.example
├── requirements.txt / pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

---

## 9. Request Lifecycle (end-to-end)

1. User fills preferences in the UI and submits.
2. UI sends `POST /recommend` with the JSON payload.
3. FastAPI validates the payload (Pydantic).
4. Integration Layer filters the store to matching candidates and shortlists top-K.
5. If no candidates → constraint relaxation loop; if still none → friendly "no matches" response.
6. Prompt is assembled with the shortlist + preferences.
7. Recommendation Engine calls the LLM (structured output).
8. Response is validated against the shortlist (anti-hallucination) and enriched with structured fields.
9. Formatted top-N + summary returned to UI.
10. UI renders recommendation cards.

---

## 10. Cross-Cutting Concerns

- **Config & secrets:** all keys/model names via env (`.env`), never hard-coded.
- **Caching:** cache identical `(filters)` shortlists and `(prompt hash)` LLM responses to cut cost/latency.
- **Cost control:** small shortlist (K), low temperature, capped `max_tokens`, request timeouts + retries with backoff.
- **Observability:** structured logging (request id, latency, token usage), plus `/health`.
- **Error handling:** graceful fallbacks — if the LLM fails, return the deterministic rating-sorted shortlist with a notice.
- **Testing:** unit-test filters/cleaning; mock the LLM for engine tests; contract-test the API.
- **Reproducibility:** pin dataset revision + dependencies; Dockerized runtime.

---

## 11. Build Milestones

1. **M1 — Ingestion:** load dataset, clean, persist to Parquet/SQLite; verify field coverage.
2. **M2 — Filtering/Repository:** implement hard-constraint filtering + shortlist logic (no LLM).
3. **M3 — LLM engine:** prompt template + provider client + structured parsing + guardrails.
4. **M4 — API:** `/recommend`, `/meta`, `/health` with validation.
5. **M5 — UI:** Streamlit form + results cards.
6. **M6 — Hardening:** caching, tests, logging, Docker, docs.

---

## 12. Future Extensions

- Semantic search / embeddings + vector store for fuzzy cuisine and free-text queries (RAG).
- User profiles and history-based personalization.
- Live data integration and geolocation / map view.
- Multi-turn conversational refinement ("cheaper", "more veg options").
- A/B testing of prompts and evaluation harness for recommendation quality.
