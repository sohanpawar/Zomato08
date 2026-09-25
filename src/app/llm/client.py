"""LLM Client Protocol and Response Containers.

Defines the pluggable LLMClient interface, response metadata,
and robust JSON extraction utilities.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from app.exceptions import LLMMalformedResponseError

T = TypeVar("T", bound=BaseModel)

# Regex to extract JSON content enclosed in markdown code fences or raw object blocks
JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


@dataclass
class LLMResponse:
    """Standardized response container and telemetry metadata from LLM generation."""

    raw_text: str
    parsed_json: dict[str, Any] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    model_name: str = ""
    provider: str = ""


def extract_json_from_text(raw_text: str) -> dict[str, Any]:
    """Extract and parse a JSON dictionary from an LLM response string.

    Handles:
        - Clean JSON strings: '{"recommendations": [...]}'
        - Markdown fenced blocks: '```json\n{"recommendations": [...]}\n```'
        - Text with conversational preamble/postamble surrounding the JSON object.

    Args:
        raw_text: Raw string returned by the LLM.

    Returns:
        dict[str, Any]: Parsed JSON dictionary.

    Raises:
        LLMMalformedResponseError: If no valid JSON dictionary could be extracted.
    """
    cleaned = raw_text.strip()
    if not cleaned:
        raise LLMMalformedResponseError(raw_text="<empty response>")

    # 1. Try direct json parsing
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 2. Check for markdown code fence ```json ... ```
    match = JSON_BLOCK_PATTERN.search(cleaned)
    if match:
        code_block = match.group(1).strip()
        try:
            parsed = json.loads(code_block)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # 3. Locate the outermost curly braces { ... }
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        substring = cleaned[first_brace : last_brace + 1]
        try:
            parsed = json.loads(substring)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    raise LLMMalformedResponseError(raw_response=raw_text)


class LLMClient(Protocol):
    """Protocol for provider-agnostic LLM completion."""

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[T],
        temperature: float = 0.2,
        max_tokens: int = 1000,
        timeout_seconds: float = 10.0,
    ) -> tuple[T, LLMResponse]:
        """Generate a structured response adhering to the Pydantic schema.

        Args:
            system_prompt: High-level behavioral and formatting instructions.
            user_prompt: Context, user preferences, and candidate data.
            response_schema: Target Pydantic model type to parse into.
            temperature: Sampling temperature.
            max_tokens: Maximum token generation budget.
            timeout_seconds: Request timeout in seconds.

        Returns:
            tuple[T, LLMResponse]: The validated Pydantic model and response metadata.
        """
        ...
