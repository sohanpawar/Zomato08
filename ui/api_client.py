"""UI API Client Module.

Communicates with the FastAPI backend service to fetch metadata, check health,
and request AI-powered recommendations with timeout controls and structured error handling.
"""

import os
from typing import Any

import httpx

from app.models.recommendation import (
    HealthResponse,
    MetadataResponse,
    RecommendationRequest,
    RecommendationResponse,
)


class BackendAPIClient:
    """Client for interacting with the FastAPI recommendation backend."""

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 15.0) -> None:
        raw_url = base_url or os.getenv("BACKEND_API_URL", "http://localhost:8000")
        self.base_url = str(raw_url).strip().strip("'\"").rstrip("/")
        self.timeout_seconds = timeout_seconds

    def check_health(self) -> dict[str, Any]:
        """Check health status of the backend API."""
        url = f"{self.base_url}/health"
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                if response.status_code == 200:
                    return response.json()
                return {"status": "degraded", "database_available": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "unreachable", "database_available": False, "error": str(e)}

    def get_metadata(self) -> MetadataResponse:
        """Fetch catalog metadata (cities, cuisines, bounds) for UI dropdown hydration."""
        url = f"{self.base_url}/meta"
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                if response.status_code == 200:
                    return MetadataResponse.model_validate(response.json())
        except Exception:
            pass

        # Safe fallback defaults if backend is unreachable during initial load
        return MetadataResponse(
            cities=["bangalore", "delhi", "mumbai", "pune", "hyderabad", "chennai", "kolkata"],
            cuisines=[
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
            ],
            budget_options=["low", "medium", "high", "any"],
            min_rating_range=(0.0, 5.0),
            max_top_n=20,
            total_restaurants=0,
        )

    def get_recommendations(self, request: RecommendationRequest) -> tuple[RecommendationResponse | None, str | None]:
        """Submit user recommendation criteria to POST /recommend.

        Returns:
            tuple[RecommendationResponse | None, str | None]: (response model, error_message if failed)
        """
        url = f"{self.base_url}/recommend"
        payload = request.model_dump()

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(url, json=payload)

                if response.status_code == 200:
                    rec_response = RecommendationResponse.model_validate(response.json())
                    return rec_response, None

                elif response.status_code == 422:
                    error_data = response.json()
                    errors = error_data.get("details", {}).get("validation_errors", [])
                    msg_list = [f"• {e.get('field')}: {e.get('message')}" for e in errors]
                    error_msg = "Validation Error:\n" + "\n".join(msg_list) if msg_list else "Invalid request data."
                    return None, error_msg

                else:
                    try:
                        err_json = response.json()
                        err_msg = err_json.get("message", f"Backend returned status {response.status_code}")
                    except Exception:
                        err_msg = f"Backend returned HTTP {response.status_code}"
                    return None, err_msg

        except httpx.ConnectError:
            return None, (
                f"Could not connect to backend server at {self.base_url}. "
                "Please make sure the FastAPI server is running (`make run-api` or `uvicorn app.main:app`)."
            )
        except httpx.TimeoutException:
            return None, f"Recommendation request timed out after {self.timeout_seconds} seconds. Please try again."
        except Exception as e:
            return None, f"An unexpected error occurred while requesting recommendations: {e}"
