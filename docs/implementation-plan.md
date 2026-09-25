# Phase-Wise Implementation Plan

## AI-Powered Restaurant Recommendation System

This plan translates the requirements in [`problemStatement.md`](./problemStatement.md) and the design in [`architecture.md`](./architecture.md) into incremental, testable delivery phases.

The target v1 stack is:

- Python 3.11+
- Hugging Face `datasets` and pandas for ingestion
- Parquet and SQLite for storage
- FastAPI and Pydantic for the backend API
- A provider-neutral LLM client with Groq as primary provider (`openai/gpt-oss-120b`, `qwen/qwen3.6-27b`)
- Streamlit for the user interface
- pytest, Ruff, Black, and mypy for quality checks
- Docker Compose for reproducible local execution

---

## 1. Delivery Principles

1. Build a deterministic recommendation path before introducing the LLM.
2. Keep dataset ingestion outside the online request path.
3. Treat the LLM as a ranking and explanation layer, not the source of restaurant facts.
4. Validate every LLM-selected restaurant against the retrieved candidate set.
5. Keep provider-specific code behind a common interface.
6. Complete each phase with tests and documented acceptance criteria.
7. Preserve a functional fallback when the LLM is unavailable.

---

## 2. Phase Overview

### Phase 0 — Project Foundation
Establish the Python project, source layout, configuration, quality tooling, and basic documentation.

### Phase 1 — Dataset Discovery and Ingestion
Inspect the Hugging Face dataset, normalize its fields, and produce reproducible processed artifacts.

### Phase 2 — Data Repository and Deterministic Retrieval
Create indexed storage, repository queries, filters, shortlisting, and constraint relaxation.

### Phase 3 — LLM Integration and Recommendation Engine
Add grounded prompts, structured LLM output, response validation, ranking, explanations, and fallback behavior.

### Phase 4 — Backend API
Expose health, metadata, and recommendation endpoints through FastAPI.

### Phase 5 — Streamlit User Interface
Build the preference form and render clear recommendation cards and status messages.

### Phase 6 — End-to-End Quality and Evaluation
Test the complete workflow, evaluate recommendation quality, and harden failure handling.

### Phase 7 — Containerization and Delivery
Package the application, document setup and operation, and create a reproducible demo environment.

### Phase 8 — Optional Production Enhancements
Add caching, richer observability, production storage, semantic retrieval, and personalization only after v1 is stable.

---

## 3. Phase 0 — Project Foundation

### Objective

Create a consistent development environment and the skeleton required by later phases.

### Tasks

#### 0.1 Initialize the project

- Create `pyproject.toml`.
- Set the minimum Python version to 3.11.
- Add runtime dependencies:
  - `datasets`
  - `pandas`
  - `pyarrow`
  - `fastapi`
  - `uvicorn`
  - `pydantic`
  - `pydantic-settings`
  - the selected LLM provider SDK
  - `streamlit`
  - `httpx`
- Add development dependencies:
  - `pytest`
  - `pytest-asyncio`
  - `pytest-cov`
  - `ruff`
  - `black`
  - `mypy`

#### 0.2 Create the source layout

Create the modules proposed by the architecture:

```text
src/app/
├── main.py
├── config.py
├── models/
├── ingestion/
├── data/
├── integration/
├── llm/providers/
└── engine/
```

Also create:

```text
data/raw/
data/processed/
scripts/
tests/unit/
tests/integration/
tests/fixtures/
ui/
```

#### 0.3 Establish configuration

- Implement a typed settings class using `pydantic-settings`.
- Read configuration from environment variables.
- Define settings for:
  - dataset name and revision
  - processed data paths
  - SQLite path
  - LLM provider and model
  - API key
  - temperature
  - maximum output tokens
  - request timeout
  - shortlist size
  - default result count
- Add `.env.example` with placeholders only.
- Ensure `.env`, generated databases, caches, and API keys are ignored by Git.

#### 0.4 Configure quality tools

- Configure Ruff rules and formatting.
- Configure Black line length consistently with Ruff.
- Enable practical mypy checks for application code.
- Add pytest configuration and coverage settings.
- Add commands for linting, formatting, type-checking, and testing.

#### 0.5 Add application conventions

- Use structured logging rather than `print`.
- Use UTC timestamps in logs where timestamps are needed.
- Define a stable exception hierarchy for:
  - configuration errors
  - repository errors
  - empty candidate results
  - LLM provider failures
  - malformed LLM responses

### Deliverables

- Installable Python project.
- Source and test directory skeleton.
- Typed settings module.
- `.env.example` and `.gitignore`.
- Working lint, format, type-check, and test commands.

### Acceptance Criteria

- A clean environment can install all dependencies.
- Importing `app` succeeds.
- Tests run even if the initial suite only contains a smoke test.
- No secret or generated dataset artifact is committed.
- Configuration fails with a clear message when required production values are absent.

---

## 4. Phase 1 — Dataset Discovery and Ingestion

### Objective

Convert the Hugging Face Zomato dataset into a clean, versioned, query-ready restaurant dataset.

### Tasks

#### 1.1 Profile the source dataset

- Load `ManikaSaini/zomato-restaurant-recommendation`.
- Pin or record the dataset revision used.
- Inspect:
  - split names
  - column names and data types
  - row count
  - null percentages
  - rating formats
  - cost formats and currency assumptions
  - location granularity
  - cuisine delimiters
  - duplicate behavior
  - availability of votes, delivery, and table-booking fields
- Record any mismatch between actual columns and the architecture assumptions.

#### 1.2 Define the canonical restaurant schema

Implement a normalized schema with:

- `id`
- `name`
- `city`
- `area`
- `cuisines`
- `cost_for_two`
- `budget_bucket`
- `rating`
- `votes`
- `features`

Document which raw fields map to each canonical field. Optional values must have explicit defaults or nullable types.

#### 1.3 Implement normalization

- Trim and normalize restaurant names.
- Normalize city and area names without losing display-friendly values.
- Split and normalize multi-value cuisines.
- Parse cost into an integer.
- Parse valid ratings into floats from 0 to 5.
- Treat values such as `NEW`, `-`, empty strings, and malformed values explicitly.
- Parse votes into non-negative integers where available.
- Map supported source attributes into `features`.
- Remove unusable records that lack critical fields.
- De-duplicate records using a documented key.
- Generate a stable ID from normalized identifying fields.

#### 1.4 Define budget buckets

- Analyze cost distribution globally and by city.
- Choose a documented rule:
  - fixed business thresholds, or
  - percentile-based thresholds.
- Prefer stable fixed thresholds for predictable user-facing behavior if the dataset supports them.
- Store the computed bucket as `low`, `medium`, or `high`.
- Add tests at every threshold boundary.

#### 1.5 Persist processed artifacts

- Write the normalized dataset to Parquet.
- Create a SQLite database from the same normalized records.
- Store cuisines and features in a queryable representation.
- Add indexes for:
  - `city`
  - `budget_bucket`
  - `rating`
  - any normalized cuisine lookup table used
- Write ingestion metadata containing:
  - source dataset and revision
  - ingestion timestamp
  - input row count
  - output row count
  - dropped row count by reason
  - duplicate count
  - schema version

#### 1.6 Make ingestion reproducible

- Implement `scripts/run_ingestion.py`.
- Make the script safe to rerun.
- Support an explicit output directory.
- Use a temporary output and atomic replacement where practical.
- Log a concise ingestion report.

### Tests

- Unit tests for cost parsing.
- Unit tests for rating parsing.
- Unit tests for cuisine normalization.
- Unit tests for stable ID generation.
- Unit tests for de-duplication.
- Unit tests for budget boundaries.
- Integration test using a small local fixture instead of downloading the full dataset.
- Schema validation test for the generated artifact.

### Deliverables

- Ingestion pipeline.
- Reusable source-to-canonical field mapping.
- `restaurants.parquet`.
- `restaurants.db`.
- Ingestion metadata/report.
- Ingestion test suite.

### Acceptance Criteria

- Running the ingestion command twice produces equivalent normalized records.
- Every output record has a stable ID, name, city, at least one cuisine, valid cost, valid rating, and budget bucket.
- Ratings fall within 0–5.
- Costs are non-negative integers.
- Duplicate policy and dropped-row reasons are measurable.
- SQLite and Parquet contain equivalent restaurant records.

### Key Decision Gate

Do not start Phase 2 until the real source schema and data quality are verified. Update the architecture if the actual dataset cannot support an assumed field such as city, votes, or features.

---

## 5. Phase 2 — Data Repository and Deterministic Retrieval

### Objective

Return a relevant shortlist from structured data without depending on an LLM.

### Tasks

#### 2.1 Implement repository interfaces

- Define a repository protocol so storage is replaceable.
- Implement SQLite as the primary repository.
- Add methods for:
  - listing cities
  - listing cuisines, optionally scoped by city
  - returning cost and rating ranges
  - retrieving candidates from a structured query
  - retrieving restaurants by stable ID
- Use parameterized SQL exclusively.

#### 2.2 Define preference models

Create typed models for:

- location
- budget
- one or more cuisines
- minimum rating
- additional preferences
- requested result count

Normalize input at the model boundary while preserving a display form for the response.

#### 2.3 Implement hard filtering

Apply:

1. exact normalized city match
2. budget bucket match
3. cuisine overlap
4. minimum rating

Return filter diagnostics containing the candidate count after each stage. Keep these diagnostics internal unless needed for debugging or user-facing relaxation notices.

#### 2.4 Implement deterministic pre-ranking

Define a transparent score using available fields, for example:

- normalized rating as the primary signal
- vote confidence as a secondary signal
- cuisine match strength
- preference/feature match
- value-for-money signal

Document the formula and avoid division by zero. Use stable tie-breaking so identical input produces identical output.

#### 2.5 Implement shortlisting

- Sort by deterministic score.
- Limit candidates to configurable top-K, initially 20.
- Ensure K is at least the requested `top_n`.
- Preserve all factual fields needed by the prompt and final response.

#### 2.6 Implement constraint relaxation

When no strict matches exist, apply a documented sequence:

1. keep location mandatory
2. relax additional feature preferences
3. allow any requested cuisine
4. lower the minimum rating in bounded steps
5. widen to an adjacent budget bucket

Never silently change constraints. Return:

- whether relaxation occurred
- which constraints changed
- the effective query

If location has no records, return a no-results outcome instead of inventing a nearby location.

### Tests

- Repository queries against a fixture database.
- SQL injection resistance through parameterized-query tests.
- Exact and case-insensitive location matching.
- Single- and multi-cuisine matching.
- Rating and budget boundary behavior.
- Stable ordering and tie-breaking.
- Top-K behavior when `top_n` is close to K.
- Every relaxation branch.
- No-result behavior for unknown locations.

### Deliverables

- Repository protocol and SQLite implementation.
- Preference/filter models.
- Deterministic filtering and pre-ranking.
- Shortlist result with diagnostics.
- Constraint-relaxation strategy.

### Acceptance Criteria

- The same request and dataset always produce the same shortlist.
- Every strict result satisfies all hard constraints.
- Every relaxed result includes a clear relaxation notice.
- Shortlisting works without an API key or network connection.
- Repository query time is acceptable for the full local dataset.

---

## 6. Phase 3 — LLM Integration and Recommendation Engine

### Objective

Use an LLM to reorder grounded candidates and produce concise explanations without allowing it to invent restaurant facts.

### Tasks

#### 3.1 Define the provider-neutral interface

Implement an `LLMClient` protocol with a method that accepts:

- system instructions
- user prompt
- structured output schema
- timeout and generation options

Return provider-independent usage and response metadata where available.

#### 3.2 Implement the Groq LLM Provider

- Implement **Groq** as the primary high-speed LLM provider for v1 (supporting models such as `openai/gpt-oss-120b` and `qwen/qwen3.6-27b`).
- Read `GROQ_API_KEY` (or `LLM_API_KEY`), `LLM_MODEL`, and base URL via typed `Settings`.
- Configure low temperature, initially `0.2`, for deterministic and grounded reasoning.
- Apply request timeout (e.g. 10.0s) and bounded retries with exponential backoff using `tenacity` / `httpx`.
- Enforce structured JSON output validation using Pydantic schemas.
- Do not retry validation errors or authentication failures.
- Map provider errors (`401`, `429`, `5xx`, timeouts) into domain application exceptions.
- Provide a Mock LLM provider for deterministic offline execution and CI.

#### 3.3 Build grounded prompts

- Include only the top-K candidates.
- Prefer stable IDs over names as the model's selection key.
- Include only fields relevant to ranking and explanation.
- State explicitly:
  - choose only from provided candidates
  - do not add facts
  - honor the requested result count
  - return the specified structured schema
- Include user preferences and any relaxation notice.
- Keep prompt construction in a separately testable module.

#### 3.4 Define structured output

Require:

- selected restaurant ID
- rank
- concise explanation
- optional match highlights
- overall summary

The final API response must source name, cuisines, rating, and cost from the repository, not from model-generated text.

#### 3.5 Validate and reconcile output

- Parse the model response with Pydantic.
- Reject or remove IDs not in the shortlist.
- Remove duplicate selections.
- Repair rank order deterministically.
- Limit results to `top_n`.
- Backfill missing valid selections from deterministic ranking if necessary.
- Sanitize excessively long explanations.
- Attach canonical restaurant facts after validation.

#### 3.6 Implement graceful fallback

If the provider is unavailable or output remains invalid:

- return deterministic top-N results
- use a template-based explanation grounded in matched fields
- include a non-sensitive notice that AI ranking was unavailable
- preserve a successful API response when useful recommendations can still be returned

#### 3.7 Add rate limits, token quotas, and caching safeguards

- Enforce client-side rate limits for `openai/gpt-oss-120b` on Groq:
  - **Requests Per Minute (RPM):** 30
  - **Requests Per Day (RPD):** 1,000 (1K)
  - **Tokens Per Minute (TPM):** 8,000 (8K)
  - **Tokens Per Day (TPD):** 200,000 (200K)
- Implement sliding-window `LLMRateLimiter` to track request timestamps and token budgets in memory.
- When approaching or exceeding rate limits, gracefully switch to deterministic heuristic fallback rather than throwing 429 errors.
- Compact candidate shortlist ($K=12$) and cap completion output (`max_tokens=600`) to guarantee every request consumes $< 800$ tokens total.
- Implement an in-memory TTL query cache (`RecommendationCache`) to serve identical requests instantly with 0 tokens consumed.
- Exclude secrets and internal stack traces from prompts and logs.
- Treat user-provided free text strictly as passive data.

### Tests

- Prompt snapshot tests.
- Structured response parsing.
- Unknown restaurant ID rejection.
- Duplicate model selection handling.
- Missing-item backfill.
- Malformed JSON handling.
- Provider timeout and rate-limit behavior.
- Deterministic fallback behavior.
- Test that final factual fields always come from the repository.

### Deliverables

- `LLMClient` protocol.
- Initial provider implementation.
- Prompt builder.
- Structured output schema.
- Recommendation orchestrator.
- Anti-hallucination validation and fallback.

### Acceptance Criteria

- The engine never returns a restaurant outside the shortlist.
- Every explanation is associated with a canonical restaurant ID.
- Invalid LLM output cannot crash the recommendation request.
- The engine returns useful deterministic results when the LLM is disabled.
- Provider-specific code does not leak into repository or API modules.

---

## 7. Phase 4 — Backend API

### Objective

Expose validated, documented endpoints for the UI and future clients.

### Tasks

#### 4.1 Application startup

- Create the FastAPI app.
- Load settings once.
- Initialize the repository and LLM client through dependency injection.
- Verify processed data is available.
- Avoid loading the Hugging Face dataset during startup.

#### 4.2 Implement `GET /health`

Return:

- application status
- data store availability
- schema/version information

Do not require an LLM request for a basic liveness check. If needed, expose readiness separately.

#### 4.3 Implement `GET /meta`

Return:

- supported locations
- cuisines
- budget options
- rating range
- allowed `top_n` range

Keep ordering stable for UI dropdowns.

#### 4.4 Implement `POST /recommend`

- Validate:
  - required location
  - supported budget enum
  - rating from 0 to 5
  - `top_n` from 1 to 20
  - bounded preference text
- Call the recommendation engine.
- Return:
  - query echo
  - effective query
  - relaxation details
  - result count
  - ranked recommendations
  - summary
  - fallback indicator where applicable

#### 4.5 Error handling

Map application errors to stable responses:

- `422` for invalid input
- `404` or a successful empty-result response for unsupported/no-data location, chosen consistently
- `503` only when no useful recommendation path is available
- `500` for unexpected failures with a request ID and no stack trace

#### 4.6 Operational controls

- Add request IDs.
- Add structured request latency logs.
- Configure CORS narrowly for the UI origin.
- Set request body limits where supported.
- Expose generated OpenAPI documentation.

### Tests

- Endpoint contract tests.
- Request validation tests.
- Health and metadata tests.
- Strict, relaxed, fallback, and no-result recommendation tests.
- Dependency override tests using a fake repository and fake LLM.
- CORS configuration test.

### Deliverables

- FastAPI application.
- Three v1 endpoints.
- OpenAPI schema.
- Stable error contracts.
- API integration test suite.

### Acceptance Criteria

- All endpoint contracts match the architecture or documented refinements.
- Invalid requests fail before repository or LLM calls.
- API tests do not require a real provider key.
- OpenAPI shows complete request and response schemas.
- A recommendation response includes all required display fields.

---

## 8. Phase 5 — Streamlit User Interface

### Objective

Provide an accessible interface for collecting preferences and displaying useful recommendations.

### Tasks

#### 5.1 Build metadata-driven controls

- Fetch `/meta` at startup and cache it briefly.
- Create controls for:
  - location
  - budget
  - one or more cuisines
  - minimum rating
  - additional preferences
  - number of results
- Disable submission until required fields are valid.

#### 5.2 Submit recommendations

- Send a typed JSON request to `/recommend`.
- Show an in-progress state.
- Set a client timeout longer than the backend provider timeout.
- Prevent accidental duplicate submissions.

#### 5.3 Render results

For each recommendation, display:

- rank
- restaurant name
- cuisines
- rating
- estimated cost for two
- AI-generated or fallback explanation

Also show:

- overall summary
- constraint-relaxation notice
- fallback notice
- friendly no-results state

#### 5.4 Handle errors

- Backend unavailable.
- Metadata unavailable.
- Validation errors.
- LLM unavailable with deterministic results returned.
- Full recommendation failure.

Do not expose raw stack traces or provider messages.

#### 5.5 Improve usability

- Preserve form values after submission.
- Use concise labels and help text.
- Format currency consistently with the dataset assumption.
- Ensure ratings and costs remain readable on narrow screens.
- Provide a reset action.

### Tests

- Unit-test request payload construction where practical.
- Mock API responses for:
  - successful recommendations
  - relaxed recommendations
  - fallback recommendations
  - empty results
  - backend errors
- Perform a manual responsive and accessibility smoke test.

### Deliverables

- Streamlit application.
- Preference form.
- Recommendation cards.
- Loading, empty, fallback, and error states.

### Acceptance Criteria

- A user can complete the full workflow without editing configuration or JSON.
- Displayed results contain all fields required by the problem statement.
- Relaxed constraints are clearly disclosed.
- UI failure states offer a useful next action.

---

## 9. Phase 6 — End-to-End Quality and Evaluation

### Objective

Demonstrate that the complete system is correct, grounded, usable, and resilient.

### Tasks

#### 6.1 Build an end-to-end test path

- Use a small deterministic dataset fixture.
- Run API calls through the complete stack.
- Use a fake structured LLM response in CI.
- Verify UI-to-API compatibility.

#### 6.2 Create an evaluation set

Prepare representative scenarios:

- popular city with common cuisine
- uncommon cuisine
- low, medium, and high budgets
- high minimum rating
- multiple cuisines
- additional preferences
- zero strict matches
- unknown location
- LLM timeout
- malformed LLM output

#### 6.3 Define quality checks

For each scenario, measure:

- constraint satisfaction
- shortlist relevance
- hallucination rate
- duplicate rate
- explanation grounding
- result count correctness
- fallback correctness
- end-to-end latency

The required hallucination rate after validation is zero.

#### 6.4 Performance and cost checks

- Measure SQLite query latency.
- Measure p50 and p95 API latency with and without LLM calls.
- Record average prompt and output token usage.
- Verify shortlist size and token limits prevent unexpectedly large requests.
- Confirm metadata calls do not invoke the LLM.

#### 6.5 Security and privacy checks

- Verify API keys are never logged or returned.
- Verify SQL is parameterized.
- Bound free-text input size.
- Test prompt-injection-like preference text.
- Ensure the model can only select candidate IDs.
- Scan dependencies for known vulnerabilities.

#### 6.6 Documentation verification

- Test setup steps on a clean environment.
- Verify all documented commands.
- Document known dataset limitations.
- Document provider-specific requirements and expected costs.

### Deliverables

- End-to-end test suite.
- Curated evaluation scenarios.
- Evaluation report.
- Performance and token-usage baseline.
- Updated operational documentation.

### Acceptance Criteria

- All critical user journeys pass.
- No returned restaurant can bypass shortlist validation.
- The deterministic fallback passes without network access.
- p95 latency and token usage are recorded and considered acceptable for the demo target.
- Setup documentation works from a clean checkout.

---

## 10. Phase 7 — Containerization and Delivery

### Objective

Make the project reproducible and easy to run for reviewers or demo users.

### Tasks

#### 7.1 Containerize services

- Create a backend Dockerfile.
- Create a Streamlit UI Dockerfile or a multi-stage project setup.
- Run as a non-root user where practical.
- Add health checks.
- Keep API keys out of image layers.

#### 7.2 Add Docker Compose

- Define backend and UI services.
- Mount or package processed data explicitly.
- Configure service-to-service URLs.
- Pass secrets through environment configuration.
- Add startup ordering based on health/readiness.

#### 7.3 Decide data distribution

Choose and document one approach:

- generate processed data during setup, or
- distribute a small approved processed snapshot, or
- download and ingest via a one-time container task.

Do not make the API container silently download and process the full dataset on every start.

#### 7.4 Add runbooks

Document:

- local Python setup
- dataset ingestion
- backend startup
- UI startup
- Docker Compose startup
- provider configuration
- running tests and quality checks
- troubleshooting missing data and provider failures

#### 7.5 Final demo verification

- Start from a clean environment.
- Run ingestion or restore the documented artifact.
- Start the stack.
- Execute one strict-match scenario.
- Execute one relaxed scenario.
- Demonstrate provider-failure fallback.

### Deliverables

- Dockerfile(s).
- `docker-compose.yml`.
- Complete README/runbook.
- Reproducible demo workflow.

### Acceptance Criteria

- One documented command starts the prepared application stack.
- Health checks become ready.
- The UI reaches the backend by service name.
- No credentials are embedded in images or source.
- The demo works with the documented dataset artifact and provider setup.

---

## 11. Phase 8 — Optional Production Enhancements

Implement these only after v1 acceptance criteria pass.

### 8.1 Caching

- Cache metadata.
- Cache deterministic shortlists by normalized query.
- Optionally cache LLM responses by prompt hash and model version.
- Define TTLs and invalidation using dataset/schema versions.

### 8.2 Observability

- Add metrics for request rate, latency, failures, fallbacks, and token usage.
- Add tracing across API, repository, and LLM calls.
- Add alerts for elevated provider errors or fallback rates.

### 8.3 Storage evolution

- Move from SQLite to PostgreSQL if concurrency or deployment requires it.
- Preserve the repository interface to minimize application changes.

### 8.4 Semantic retrieval

- Add embeddings only when exact cuisine/location filters are insufficient.
- Keep hard filters for location, budget, and minimum rating.
- Evaluate semantic retrieval against the deterministic baseline.

### 8.5 Personalization

- Add accounts and preference history.
- Obtain explicit consent before storing profile data.
- Separate user data from restaurant catalog data.

### 8.6 Conversational refinement

- Support follow-up requests such as “cheaper” or “more vegetarian options.”
- Convert each turn into an explicit structured preference update.
- Avoid relying solely on unconstrained conversation history.

---

## 12. Cross-Phase Testing Strategy

### Unit tests

Cover pure transformations and business rules:

- parsing and normalization
- budget categorization
- filtering
- deterministic scoring
- constraint relaxation
- prompt construction
- LLM output reconciliation
- API model validation

### Integration tests

Cover boundaries:

- ingestion to SQLite/Parquet
- repository against SQLite
- engine with fake LLM provider
- FastAPI with dependency overrides
- UI request client with mocked backend

### End-to-end tests

Cover the complete preference-to-display workflow using stable fixtures. Keep real paid LLM tests outside the default CI suite and mark them explicitly.

### Regression fixtures

Store small, license-compatible fixtures that include malformed ratings, malformed costs, duplicates, multiple cuisines, missing optional fields, and filter edge cases.

---

## 13. Definition of Done for v1

The v1 project is complete when:

- [ ] The Zomato dataset can be ingested reproducibly.
- [ ] Processed restaurants conform to the canonical schema.
- [ ] SQLite filtering supports location, budget, cuisine, and minimum rating.
- [ ] Deterministic ranking produces a bounded top-K shortlist.
- [ ] The LLM ranks only supplied candidate IDs.
- [ ] Every returned fact is sourced from structured data.
- [ ] Explanations and an overall summary are returned.
- [ ] Invalid or unavailable LLM output falls back safely.
- [ ] `/health`, `/meta`, and `/recommend` are documented and tested.
- [ ] Streamlit collects all required preferences.
- [ ] The UI displays name, cuisine, rating, cost, and explanation.
- [ ] Constraint relaxation is visible to the user.
- [ ] Unit, integration, and end-to-end tests pass.
- [ ] Linting, formatting, and type checks pass.
- [ ] Secrets are environment-driven and absent from source control.
- [ ] Docker-based startup and local startup are documented.

---

## 14. Recommended Execution Order

Complete phases sequentially because each creates an interface required by the next:

1. Foundation
2. Dataset ingestion
3. Repository and deterministic retrieval
4. LLM recommendation engine
5. Backend API
6. Streamlit UI
7. End-to-end quality
8. Containerized delivery

The key checkpoint is the end of Phase 2: the system must already return useful deterministic recommendations. This keeps the LLM integration measurable, replaceable, and non-critical to basic availability.
