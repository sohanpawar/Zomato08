"""Mock LLM Provider Implementation.

Provides a fast, deterministic, offline LLM client for unit tests, CI pipelines,
and evaluation suites without external network calls or API costs.
"""

import asyncio
import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel

from app.exceptions import LLMAuthenticationError, LLMMalformedResponseError, LLMTimeoutError
from app.llm.client import LLMResponse
from app.models.recommendation import LLMSelectedRecommendation, LLMStructuredOutput

T = TypeVar("T", bound=BaseModel)


class MockLLMClient:
    """Deterministic Mock LLM Client for testing."""

    def __init__(
        self,
        preset_response: BaseModel | None = None,
        preset_raw_text: str | None = None,
        simulate_latency_ms: float = 10.0,
        simulate_timeout: bool = False,
        simulate_auth_error: bool = False,
        simulate_malformed: bool = False,
        simulate_hallucination: bool = False,
    ) -> None:
        self.preset_response = preset_response
        self.preset_raw_text = preset_raw_text
        self.simulate_latency_ms = simulate_latency_ms
        self.simulate_timeout = simulate_timeout
        self.simulate_auth_error = simulate_auth_error
        self.simulate_malformed = simulate_malformed
        self.simulate_hallucination = simulate_hallucination
        self.call_history: list[dict[str, Any]] = []

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[T],
        temperature: float = 0.2,
        max_tokens: int = 1000,
        timeout_seconds: float = 10.0,
        api_key_override: str | None = None,
    ) -> tuple[T, LLMResponse]:
        """Simulate structured LLM response generation."""
        self.call_history.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "response_schema": response_schema,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout_seconds": timeout_seconds,
        })

        if self.simulate_timeout:
            raise LLMTimeoutError(timeout_seconds=timeout_seconds)

        if self.simulate_auth_error:
            raise LLMAuthenticationError(provider="mock")

        if self.simulate_malformed:
            raise LLMMalformedResponseError(raw_response="INVALID NON-JSON OUTPUT ###")

        if self.simulate_latency_ms > 0:
            await asyncio.sleep(self.simulate_latency_ms / 1000.0)

        # 1. If preset response provided
        if self.preset_response is not None:
            raw_text = self.preset_raw_text or self.preset_response.model_dump_json()
            return self.preset_response, LLMResponse(  # type: ignore[return-value]
                raw_text=raw_text,
                parsed_json=self.preset_response.model_dump(),
                prompt_tokens=150,
                completion_tokens=80,
                total_tokens=230,
                latency_ms=self.simulate_latency_ms,
                model_name="mock-model",
                provider="mock",
            )

        # 2. Extract candidate IDs from user prompt to simulate realistic selection
        id_matches = re.findall(r'"id":\s*"([^"]+)"', user_prompt)
        selected_ids = id_matches[:5] if id_matches else ["rest_mock_001"]

        if self.simulate_hallucination:
            selected_ids.insert(0, "rest_hallucinated_ghost_id_999")

        recommendations = [
            LLMSelectedRecommendation(
                id=r_id,
                rank=idx + 1,
                explanation=f"Excellent fit matching your preferences with outstanding ratings and great value.",
                highlights=["Top Pick", "Authentic"],
            )
            for idx, r_id in enumerate(selected_ids)
        ]

        structured = LLMStructuredOutput(
            recommendations=recommendations,
            summary="Personalized recommendations curated from your selected preferences.",
        )

        validated = response_schema.model_validate(structured.model_dump())
        llm_resp = LLMResponse(
            raw_text=structured.model_dump_json(indent=2),
            parsed_json=structured.model_dump(),
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            latency_ms=self.simulate_latency_ms,
            model_name="mock-model",
            provider="mock",
        )

        return validated, llm_resp
