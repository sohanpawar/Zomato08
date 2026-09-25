"""Unit tests for configuration loading and validation."""

from pathlib import Path
import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


def test_default_settings_instantiation() -> None:
    """Verify default settings instantiation."""
    settings = Settings()
    assert settings.app_env in {"development", "staging", "production", "test"}
    assert settings.dataset_name == "ManikaSaini/zomato-restaurant-recommendation"
    assert settings.shortlist_size == 20
    assert settings.default_top_n == 5
    assert settings.llm_provider in {"groq", "gemini", "openai", "ollama", "mock"}
    assert settings.log_level == "INFO"


def test_effective_api_key_resolution() -> None:
    """Verify effective API key resolves groq_api_key or llm_api_key."""
    s1 = Settings(llm_provider="groq", groq_api_key="gsk_123")
    assert s1.effective_api_key == "gsk_123"

    s2 = Settings(llm_provider="groq", llm_api_key="generic_key")
    assert s2.effective_api_key == "generic_key"

    s3 = Settings(llm_provider="openai", llm_api_key="sk-openai")
    assert s3.effective_api_key == "sk-openai"


def test_custom_settings_overrides(tmp_path: Path) -> None:
    """Verify custom settings values override defaults."""
    custom = Settings(
        app_env="test",
        debug=True,
        log_level="DEBUG",
        shortlist_size=15,
        default_top_n=3,
        llm_provider="mock",
        raw_data_dir=tmp_path / "raw",
        processed_data_dir=tmp_path / "processed",
    )
    assert custom.app_env == "test"
    assert custom.debug is True
    assert custom.shortlist_size == 15
    assert custom.default_top_n == 3
    assert custom.llm_provider == "mock"


def test_invalid_log_level_raises_validation_error() -> None:
    """Verify invalid log level string is rejected by validator."""
    with pytest.raises(ValidationError):
        Settings(log_level="INVALID_LEVEL")


def test_ensure_directories_exist(tmp_path: Path) -> None:
    """Verify ensure_directories_exist creates raw and processed folders."""
    raw_dir = tmp_path / "new_raw"
    proc_dir = tmp_path / "new_processed"
    assert not raw_dir.exists()
    assert not proc_dir.exists()

    settings = Settings(raw_data_dir=raw_dir, processed_data_dir=proc_dir)
    settings.ensure_directories_exist()

    assert raw_dir.is_dir()
    assert proc_dir.is_dir()


def test_get_settings_cached_singleton() -> None:
    """Verify get_settings returns the same cached instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
