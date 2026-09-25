"""Application Configuration Settings.

Uses Pydantic Settings to load and validate environment variables from `.env`
and the host environment, enforcing typed configurations.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide typed configuration settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --------------------------------------------------------------------------
    # Environment & Application
    # --------------------------------------------------------------------------
    app_env: Literal["development", "staging", "production", "test"] = Field(
        default="development",
        description="Current runtime environment.",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode and detailed error traces.",
    )
    log_level: str = Field(
        default="INFO",
        description="Application log level (DEBUG, INFO, WARNING, ERROR).",
    )
    json_logs: bool = Field(
        default=False,
        description="Format application logs as JSON lines for structured logging.",
    )
    api_host: str = Field(
        default="0.0.0.0",
        description="Host address for FastAPI backend.",
    )
    api_port: int = Field(
        default=8000,
        description="Port for FastAPI backend server.",
    )
    cors_origins: list[str] = Field(
        default=["http://localhost:8501", "http://127.0.0.1:8501"],
        description="Allowed CORS origins (e.g., Streamlit UI).",
    )

    # --------------------------------------------------------------------------
    # Dataset & Storage
    # --------------------------------------------------------------------------
    dataset_name: str = Field(
        default="ManikaSaini/zomato-restaurant-recommendation",
        description="Hugging Face dataset identifier.",
    )
    dataset_revision: str | None = Field(
        default="main",
        description="Hugging Face dataset branch/commit revision.",
    )
    raw_data_dir: Path = Field(
        default=Path("data/raw"),
        description="Directory for cached raw dataset files.",
    )
    processed_data_dir: Path = Field(
        default=Path("data/processed"),
        description="Directory for processed Parquet and SQLite artifacts.",
    )
    sqlite_path: Path = Field(
        default=Path("data/processed/restaurants.db"),
        description="Path to SQLite database for fast indexed retrieval.",
    )
    parquet_path: Path = Field(
        default=Path("data/processed/restaurants.parquet"),
        description="Path to Parquet file for analytics and data inspection.",
    )

    # --------------------------------------------------------------------------
    # Retrieval & Shortlisting Settings
    # --------------------------------------------------------------------------
    shortlist_size: int = Field(
        default=12,
        ge=3,
        le=50,
        description="Number of candidate restaurants (K) passed into the LLM prompt (compact for token budget).",
    )
    default_top_n: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Default number of final recommendations returned to user.",
    )
    max_top_n: int = Field(
        default=20,
        ge=1,
        le=20,
        description="Maximum allowed top_n requested by a client.",
    )

    # --------------------------------------------------------------------------
    # LLM Provider Configuration (openai/gpt-oss-120b on Groq)
    # --------------------------------------------------------------------------
    llm_provider: Literal["groq", "openai", "gemini", "ollama", "mock"] = Field(
        default="groq",
        description="Active LLM provider for ranking and explanation generation.",
    )
    llm_model: str = Field(
        default="openai/gpt-oss-120b",
        description="Model name/slug passed to the LLM provider API.",
    )
    llm_api_key: str | None = Field(
        default=None,
        description="General API key for hosted LLM providers.",
    )
    groq_api_key: str | None = Field(
        default=None,
        description="Dedicated API key for Groq Cloud API.",
    )
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        description="Base API endpoint URL for Groq inference.",
    )
    llm_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for LLM reasoning (kept low for grounding).",
    )
    llm_max_tokens: int = Field(
        default=600,
        ge=100,
        le=4000,
        description="Maximum token budget for LLM response generation (capped for token quota conservation).",
    )
    llm_timeout_seconds: float = Field(
        default=10.0,
        ge=1.0,
        le=60.0,
        description="Maximum duration to wait for LLM completion before fallback.",
    )
    llm_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Maximum retry attempts on transient LLM failures (e.g. rate limit).",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL when using Ollama for local LLM inference.",
    )

    # --------------------------------------------------------------------------
    # LLM Quota & Rate Limit Settings (openai/gpt-oss-120b: 30 RPM, 1K RPD, 8K TPM, 200K TPD)
    # --------------------------------------------------------------------------
    rate_limit_rpm: int = Field(
        default=30,
        description="Max allowed requests per minute to Groq API.",
    )
    rate_limit_rpd: int = Field(
        default=1000,
        description="Max allowed requests per day to Groq API.",
    )
    rate_limit_tpm: int = Field(
        default=8000,
        description="Max allowed tokens per minute to Groq API.",
    )
    rate_limit_tpd: int = Field(
        default=200000,
        description="Max allowed tokens per day to Groq API.",
    )

    @property
    def effective_api_key(self) -> str | None:
        """Resolve the effective API key based on the active provider."""
        if self.llm_provider == "groq":
            return self.groq_api_key or self.llm_api_key
        return self.llm_api_key

    # --------------------------------------------------------------------------
    # Frontend Settings
    # --------------------------------------------------------------------------
    backend_api_url: str = Field(
        default="http://localhost:8000",
        description="URL used by Streamlit frontend to communicate with FastAPI.",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        """Parse CORS origins from JSON array, comma-separated string, or list."""
        if isinstance(v, str):
            v_clean = v.strip()
            if not v_clean:
                return ["*"]
            if v_clean.startswith("[") and v_clean.endswith("]"):
                try:
                    import json
                    parsed = json.loads(v_clean)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            # Comma-separated fallback e.g. "https://app1.com, https://app2.com"
            return [item.strip() for item in v_clean.split(",") if item.strip()]
        elif isinstance(v, (list, tuple, set)):
            return [str(item).strip() for item in v if str(item).strip()]
        return ["*"]

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"Invalid log_level: {v}. Must be one of {valid_levels}")
        return upper_v

    def ensure_directories_exist(self) -> None:
        """Create required data directories if they do not exist."""
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.processed_data_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton factory."""
    settings = Settings()
    return settings
