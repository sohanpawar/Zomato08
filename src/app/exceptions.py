"""Structured Application Exception Hierarchy.

Provides distinct, typed exceptions across configuration, data repository,
LLM orchestration, validation, and API layers.
"""

from typing import Any


class AppError(Exception):
    """Base exception for all application errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_APP_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize error details for API responses and logs."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


# ==============================================================================
# Configuration Exceptions
# ==============================================================================


class ConfigurationError(AppError):
    """Raised when application settings or environment variables are invalid."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            status_code=500,
            details=details,
        )


# ==============================================================================
# Data & Ingestion Exceptions
# ==============================================================================


class DataError(AppError):
    """Base class for data pipeline and storage errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "DATA_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details=details,
        )


class DataIngestionError(DataError):
    """Raised when downloading, parsing, or saving raw dataset fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="DATA_INGESTION_ERROR",
            status_code=500,
            details=details,
        )


class DatasetNotFoundError(DataError):
    """Raised when processed dataset or SQLite database is missing on disk."""

    def __init__(self, path: str, details: dict[str, Any] | None = None) -> None:
        details = details or {}
        details["path"] = path
        super().__init__(
            message=f"Processed dataset artifact not found at: {path}",
            error_code="DATASET_NOT_FOUND",
            status_code=503,
            details=details,
        )


# ==============================================================================
# Repository & Retrieval Exceptions
# ==============================================================================


class RepositoryError(AppError):
    """Base class for database querying and candidate retrieval errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "REPOSITORY_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details=details,
        )


class RestaurantNotFoundError(RepositoryError):
    """Raised when a specific restaurant ID is not found in the database."""

    def __init__(self, restaurant_id: str) -> None:
        super().__init__(
            message=f"Restaurant with ID '{restaurant_id}' was not found.",
            error_code="RESTAURANT_NOT_FOUND",
            status_code=404,
            details={"restaurant_id": restaurant_id},
        )


class EmptyCandidatesError(RepositoryError):
    """Raised when filtering produces 0 candidates and relaxation is exhausted."""

    def __init__(self, location: str, details: dict[str, Any] | None = None) -> None:
        details = details or {}
        details["location"] = location
        super().__init__(
            message=f"No matching restaurants found in location '{location}'.",
            error_code="EMPTY_CANDIDATES",
            status_code=200,  # Graceful return with empty recommendations
            details=details,
        )


# ==============================================================================
# LLM Provider & Generation Exceptions
# ==============================================================================


class LLMError(AppError):
    """Base class for LLM client and inference errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "LLM_ERROR",
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details=details,
        )


class LLMProviderError(LLMError):
    """Raised when LLM API returns an unhandled error or server error."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="LLM_PROVIDER_ERROR",
            status_code=502,
            details=details,
        )


class LLMTimeoutError(LLMError):
    """Raised when an LLM request exceeds configured timeout threshold."""

    def __init__(self, timeout_seconds: float) -> None:
        super().__init__(
            message=f"LLM request timed out after {timeout_seconds} seconds.",
            error_code="LLM_TIMEOUT",
            status_code=504,
            details={"timeout_seconds": timeout_seconds},
        )


class LLMMalformedResponseError(LLMError):
    """Raised when LLM returns invalid JSON or fails schema validation."""

    def __init__(self, raw_response: str, details: dict[str, Any] | None = None) -> None:
        details = details or {}
        details["raw_response_preview"] = raw_response[:300]
        super().__init__(
            message="LLM returned a response that could not be parsed into the expected schema.",
            error_code="LLM_MALFORMED_RESPONSE",
            status_code=502,
            details=details,
        )


class LLMAuthenticationError(LLMError):
    """Raised when LLM provider rejects API key or authentication credentials."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            message=f"Authentication failed for LLM provider: {provider}. Please check your API key.",
            error_code="LLM_AUTH_ERROR",
            status_code=401,
            details={"provider": provider},
        )


class HallucinationDetectedError(LLMError):
    """Raised internally when an LLM selects IDs not in the candidate shortlist."""

    def __init__(self, invalid_ids: list[str]) -> None:
        super().__init__(
            message=f"LLM hallucinated restaurant IDs not present in shortlist: {invalid_ids}",
            error_code="HALLUCINATION_DETECTED",
            status_code=500,
            details={"invalid_ids": invalid_ids},
        )


# ==============================================================================
# Input & Validation Exceptions
# ==============================================================================


class InputValidationError(AppError):
    """Raised when user input fails business rule validation."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=message,
            error_code="INPUT_VALIDATION_ERROR",
            status_code=422,
            details=details,
        )


class PromptInjectionError(InputValidationError):
    """Raised when user input contains adversarial prompt injection patterns."""

    def __init__(self, pattern: str) -> None:
        super().__init__(
            message="Input text contained disallowed prompt injection patterns.",
            details={"detected_pattern": pattern},
        )
        self.error_code = "PROMPT_INJECTION_DETECTED"
        self.status_code = 400
