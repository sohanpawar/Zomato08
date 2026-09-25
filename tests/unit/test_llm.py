"""Unit Tests for LLM Providers, JSON Extraction, and Factory."""

import pytest

from app.config import Settings
from app.exceptions import (
    ConfigurationError,
    LLMAuthenticationError,
    LLMMalformedResponseError,
    LLMTimeoutError,
)
from app.llm.client import extract_json_from_text
from app.llm.factory import get_llm_client
from app.llm.providers.groq import GroqLLMClient
from app.llm.providers.mock import MockLLMClient
from app.models.recommendation import LLMStructuredOutput


def test_extract_json_from_clean_text() -> None:
    """Verify clean JSON string parsing."""
    raw = '{"recommendations": [{"id": "rest_1", "rank": 1, "explanation": "Great food"}], "summary": "Top pick"}'
    parsed = extract_json_from_text(raw)
    assert parsed["summary"] == "Top pick"
    assert len(parsed["recommendations"]) == 1


def test_extract_json_from_markdown_code_fence() -> None:
    """Verify JSON enclosed in ```json ... ``` code fence."""
    raw = """Here is the recommended list:
```json
{
  "recommendations": [
    {
      "id": "rest_blr_001",
      "rank": 1,
      "explanation": "Authentic dining experience with great pasta."
    }
  ],
  "summary": "Best Italian in Bangalore"
}
```
Hope you enjoy!"""
    parsed = extract_json_from_text(raw)
    assert parsed["summary"] == "Best Italian in Bangalore"
    assert parsed["recommendations"][0]["id"] == "rest_blr_001"


def test_extract_json_malformed_raises_error() -> None:
    """Verify non-JSON strings raise LLMMalformedResponseError."""
    with pytest.raises(LLMMalformedResponseError):
        extract_json_from_text("Sorry, I cannot recommend any restaurants.")


@pytest.mark.asyncio
async def test_mock_llm_client_generation() -> None:
    """Verify MockLLMClient generates valid structured output matching candidate IDs."""
    client = MockLLMClient()
    user_prompt = 'Candidate list: [{"id": "rest_blr_001", "name": "Toscano"}]'

    output, telemetry = await client.generate_structured(
        system_prompt="Test system prompt",
        user_prompt=user_prompt,
        response_schema=LLMStructuredOutput,
    )

    assert isinstance(output, LLMStructuredOutput)
    assert len(output.recommendations) >= 1
    assert output.recommendations[0].id == "rest_blr_001"
    assert telemetry.provider == "mock"
    assert telemetry.latency_ms >= 0.0


@pytest.mark.asyncio
async def test_mock_llm_client_simulated_errors() -> None:
    """Verify Mock client simulates timeout, auth, and malformed errors."""
    # Timeout
    timeout_client = MockLLMClient(simulate_timeout=True)
    with pytest.raises(LLMTimeoutError):
        await timeout_client.generate_structured("sys", "user", LLMStructuredOutput)

    # Auth Error
    auth_client = MockLLMClient(simulate_auth_error=True)
    with pytest.raises(LLMAuthenticationError):
        await auth_client.generate_structured("sys", "user", LLMStructuredOutput)

    # Malformed JSON Error
    malformed_client = MockLLMClient(simulate_malformed=True)
    with pytest.raises(LLMMalformedResponseError):
        await malformed_client.generate_structured("sys", "user", LLMStructuredOutput)


def test_llm_factory_instantiates_groq_and_mock() -> None:
    """Verify get_llm_client instantiates correct client based on settings."""
    groq_settings = Settings(llm_provider="groq", groq_api_key="gsk_test123")
    groq_client = get_llm_client(groq_settings)
    assert isinstance(groq_client, GroqLLMClient)

    mock_settings = Settings(llm_provider="mock")
    mock_client = get_llm_client(mock_settings)
    assert isinstance(mock_client, MockLLMClient)


def test_llm_factory_unsupported_provider() -> None:
    """Verify invalid provider raises ConfigurationError."""
    bad_settings = Settings.model_construct(llm_provider="unsupported_provider")
    with pytest.raises(ConfigurationError):
        get_llm_client(bad_settings)
