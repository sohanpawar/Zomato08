"""Groq LLM Provider Implementation.

Provides ultra-fast inference using the Groq Cloud API, supporting models such as
'openai/gpt-oss-120b' and 'qwen/qwen3.6-27b', with
automatic JSON mode enforcement, exponential retry backoff, and latency tracking.
"""

import asyncio
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings
from app.exceptions import (
    LLMAuthenticationError,
    LLMMalformedResponseError,
    LLMProviderError,
    LLMTimeoutError,
)
from app.llm.client import LLMResponse, extract_json_from_text
from app.llm.rate_limiter import LLMRateLimiter, RateLimitExceededError
from app.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


def is_retryable_error(exc: BaseException) -> bool:
    """Determine if an exception should trigger a retry attempt."""
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        # Retry on 429 (Rate Limit) and 5xx (Server Errors)
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return False


class GroqLLMClient:
    """Groq Cloud API Client implementing the LLMClient protocol with quota rate limiting."""

    def __init__(
        self,
        settings: Settings,
        rate_limiter: LLMRateLimiter | None = None,
    ) -> None:
        self.settings = settings
        self.api_key = settings.effective_api_key
        self.model = settings.llm_model or "openai/gpt-oss-120b"
        self.base_url = settings.groq_base_url.rstrip("/")
        self.rate_limiter = rate_limiter or LLMRateLimiter(
            max_rpm=settings.rate_limit_rpm,
            max_rpd=settings.rate_limit_rpd,
            max_tpm=settings.rate_limit_tpm,
            max_tpd=settings.rate_limit_tpd,
        )

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[T],
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
        api_key_override: str | None = None,
    ) -> tuple[T, LLMResponse]:
        """Send a structured completion request to the Groq API and parse into a Pydantic schema."""
        effective_key = api_key_override or self.api_key
        if not effective_key:
            raise LLMAuthenticationError(
                provider="groq"
            )

        temp = temperature if temperature is not None else self.settings.llm_temperature
        tokens = max_tokens if max_tokens is not None else self.settings.llm_max_tokens
        timeout = timeout_seconds if timeout_seconds is not None else self.settings.llm_timeout_seconds
        max_retries = self.settings.llm_max_retries

        # Estimate token usage (~3.5 characters per token) to check rate limits before invoking API
        estimated_prompt_tokens = len(system_prompt + user_prompt) // 3
        estimated_total_tokens = estimated_prompt_tokens + tokens

        # 1. Rate Limiter Guard (30 RPM, 1K RPD, 8K TPM, 200K TPD)
        acquired = await self.rate_limiter.check_and_acquire(estimated_tokens=estimated_total_tokens)
        if not acquired:
            stats = await self.rate_limiter.get_stats()
            raise RateLimitExceededError(
                reason="Groq RPM/TPM quota threshold reached",
                details={
                    "current_rpm": stats.current_rpm,
                    "max_rpm": stats.max_rpm,
                    "current_tpm": stats.current_tpm,
                    "max_tpm": stats.max_tpm,
                },
            )

        headers = {
            "Authorization": f"Bearer {effective_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temp,
            "max_tokens": tokens,
            "response_format": {"type": "json_object"},
        }

        endpoint_url = f"{self.base_url}/chat/completions"
        start_time = time.perf_counter()
        raw_content = ""
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        async def _call_api() -> httpx.Response:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(endpoint_url, headers=headers, json=payload)
                if response.status_code in {401, 403}:
                    raise LLMAuthenticationError(provider="groq")
                response.raise_for_status()
                return response

        try:
            # Execute with exponential backoff retry on transient errors
            if max_retries > 0:
                retrying = AsyncRetrying(
                    stop=stop_after_attempt(max_retries + 1),
                    wait=wait_exponential(multiplier=0.5, min=1.0, max=4.0),
                    retry=retry_if_exception(is_retryable_error),
                    reraise=True,
                )
                http_response = await retrying(_call_api)
            else:
                http_response = await _call_api()

            duration_ms = (time.perf_counter() - start_time) * 1000
            data = http_response.json()

            # Extract generated content and usage telemetry
            choices = data.get("choices", [])
            if not choices:
                raise LLMProviderError("Groq returned empty choices list in response.")

            raw_content = choices[0].get("message", {}).get("content", "")

            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", estimated_prompt_tokens)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

            # Reconcile actual tokens consumed with rate limiter
            await self.rate_limiter.record_actual_usage(
                actual_tokens=total_tokens,
                estimated_tokens_reserved=estimated_total_tokens,
            )

        except httpx.TimeoutException as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.warning("Groq request timed out after %.2fs", timeout)
            raise LLMTimeoutError(timeout_seconds=timeout) from e
        except LLMAuthenticationError:
            raise
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Groq API error: %s", str(e), exc_info=True)
            raise LLMProviderError(f"Groq API call failed: {e}", details={"model": self.model}) from e

        # Extract and parse JSON into the Pydantic schema
        try:
            parsed_dict = extract_json_from_text(raw_content)
            validated_model = response_schema.model_validate(parsed_dict)
        except (LLMMalformedResponseError, ValidationError) as e:
            logger.warning("Failed to validate Groq JSON against schema: %s", str(e))
            raise LLMMalformedResponseError(
                raw_response=raw_content,
                details={"validation_error": str(e), "model": self.model},
            ) from e

        llm_response = LLMResponse(
            raw_text=raw_content,
            parsed_json=parsed_dict,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=round(duration_ms, 2),
            model_name=self.model,
            provider="groq",
        )

        return validated_model, llm_response
