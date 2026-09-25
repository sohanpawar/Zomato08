"""FastAPI Application Entry Point.

Initializes the API server, registers routes, sets up CORS middleware,
and configures global structured exception handlers and dependency injection.
"""

import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import Settings, get_settings
from app.data.repository import RestaurantRepository
from app.dependencies import (
    get_app_settings,
    get_recommendation_engine,
    get_repository,
)
from app.engine.recommender import RecommendationEngine
from app.exceptions import AppError
from app.logging import get_logger, setup_logging
from app.models.recommendation import (
    HealthResponse,
    MetadataResponse,
    RecommendationRequest,
    RecommendationResponse,
)

logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup and shutdown hooks."""
    from pathlib import Path

    settings = get_settings()
    setup_logging(level=settings.log_level, json_format=settings.json_logs)
    logger.info("Initializing NextLeap Restaurant Recommendation API (v%s)", __version__)

    # Ensure required data directories exist
    settings.ensure_directories_exist()

    # Pre-seed sample catalog if database is empty or not found on first boot
    repo = get_repository(settings)
    if not repo.is_available() or repo.count_total() == 0:
        logger.warning("Database empty or missing at %s. Attempting initial seeding...", settings.sqlite_path)
        try:
            from app.ingestion.pipeline import IngestionPipeline

            pipeline = IngestionPipeline(settings=settings)
            sample_fixtures = [
                Path("tests/fixtures/sample_raw_hf_zomato.json"),
                Path("tests/fixtures/sample_restaurants.json"),
            ]
            for fixture in sample_fixtures:
                if fixture.is_file():
                    logger.info("Seeding database using fixture: %s", fixture)
                    pipeline.run(local_file=fixture, force_reload=True)
                    break
            logger.info("Database initialized successfully. Total restaurants: %d", repo.count_total())
        except Exception as e:
            logger.warning("Auto-seeding during startup failed (will rely on mounted DB/manual ingestion): %s", e)

    yield

    logger.info("Shutting down API server.")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    settings = get_settings()

    app = FastAPI(
        title="AI-Powered Restaurant Recommendation API",
        description="Personalized restaurant suggestions combining structured Zomato data with LLM reasoning.",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # --------------------------------------------------------------------------
    # CORS Middleware
    # --------------------------------------------------------------------------
    is_wildcard = "*" in settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=not is_wildcard,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --------------------------------------------------------------------------
    # Request ID & Latency Middleware
    # --------------------------------------------------------------------------
    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start_time = time.perf_counter()

        # Attach request_id to state
        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

        return response

    # --------------------------------------------------------------------------
    # Global Exception Handlers
    # --------------------------------------------------------------------------
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "unknown")
        errors: list[dict[str, Any]] = []
        for error in exc.errors():
            loc = " -> ".join(str(x) for x in error.get("loc", []))
            errors.append({
                "field": loc,
                "message": error.get("msg", "Invalid value"),
                "type": error.get("type", "value_error"),
            })

        logger.warning(
            "Request validation failed: %s",
            errors,
            extra={"request_id": req_id},
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error_code": "REQUEST_VALIDATION_ERROR",
                "message": "Input validation failed. Please check the provided fields.",
                "details": {"validation_errors": errors},
                "request_id": req_id,
            },
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "unknown")
        logger.warning(
            "Application error [%s]: %s (Status: %d)",
            exc.error_code,
            exc.message,
            exc.status_code,
            extra={"request_id": req_id, "extra_data": exc.details},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
                "request_id": req_id,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", "unknown")
        logger.error(
            "Unhandled server error: %s",
            str(exc),
            exc_info=True,
            extra={"request_id": req_id},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
                "request_id": req_id,
            },
        )

    # --------------------------------------------------------------------------
    # API Routes
    # --------------------------------------------------------------------------
    @app.get(
        "/health",
        response_model=HealthResponse,
        summary="Application health check",
        tags=["System"],
    )
    async def health_check(
        repository: RestaurantRepository = Depends(get_repository),
    ) -> HealthResponse:
        """Health check endpoint indicating database availability and system version."""
        db_available = repository.is_available()
        total_restaurants = repository.count_total() if db_available else 0

        return HealthResponse(
            status="healthy" if db_available else "degraded",
            database_available=db_available,
            total_restaurants=total_restaurants,
            version=__version__,
        )

    @app.get(
        "/meta",
        response_model=MetadataResponse,
        summary="Catalog metadata for UI dropdowns",
        tags=["Catalog"],
    )
    async def get_metadata(
        repository: RestaurantRepository = Depends(get_repository),
        settings: Settings = Depends(get_app_settings),
    ) -> MetadataResponse:
        """Returns supported cities, cuisines, and bounds to dynamically hydrate frontend dropdowns."""
        db_available = repository.is_available()

        if db_available:
            cities = repository.list_cities()
            cuisines = repository.list_cuisines()
            total_restaurants = repository.count_total()
        else:
            cities = []
            cuisines = []
            total_restaurants = 0

        # Fallback defaults if catalog is newly initialized / empty
        if not cities:
            cities = ["bangalore", "delhi", "mumbai", "pune", "hyderabad", "chennai", "kolkata"]
        if not cuisines:
            cuisines = [
                "North Indian",
                "Chinese",
                "South Indian",
                "Italian",
                "Fast Food",
                "Continental",
                "Cafe",
                "Desserts",
                "Biryani",
                "Mughlai",
            ]

        return MetadataResponse(
            cities=cities,
            cuisines=cuisines,
            budget_options=["low", "medium", "high", "any"],
            min_rating_range=(0.0, 5.0),
            max_top_n=settings.max_top_n,
            total_restaurants=total_restaurants,
        )

    @app.post(
        "/recommend",
        response_model=RecommendationResponse,
        summary="Generate personalized restaurant recommendations",
        tags=["Recommendations"],
    )
    async def get_recommendations(
        request: RecommendationRequest,
        engine: RecommendationEngine = Depends(get_recommendation_engine),
    ) -> RecommendationResponse:
        """Main recommendation endpoint combining deterministic retrieval with LLM reasoning."""
        return await engine.recommend(request)

    return app


app = create_app()
