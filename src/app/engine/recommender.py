"""Recommendation Engine Orchestrator.

Orchestrates candidate filtering, grounded prompt construction, structured LLM reasoning,
strict anti-hallucination validation, canonical metadata hydration, and resilient heuristic fallback.
"""

from typing import Any

from app.config import Settings, get_settings
from app.engine.cache import RecommendationCache
from app.exceptions import LLMError
from app.integration.filters import CandidateFilterService, FilterResult
from app.integration.prompt import PromptBuilder
from app.llm.client import LLMClient
from app.llm.factory import get_llm_client
from app.logging import get_logger
from app.models.recommendation import (
    LLMStructuredOutput,
    RecommendationItem,
    RecommendationRequest,
    RecommendationResponse,
)
from app.models.restaurant import Restaurant

logger = get_logger(__name__)


class RecommendationEngine:
    """Core orchestrator executing end-to-end personalized restaurant recommendation."""

    def __init__(
        self,
        filter_service: CandidateFilterService,
        prompt_builder: PromptBuilder | None = None,
        llm_client: LLMClient | None = None,
        cache: RecommendationCache | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.filter_service = filter_service
        self.settings = settings or get_settings()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.llm_client = llm_client or get_llm_client(self.settings)
        self.cache = cache or RecommendationCache()

    def _generate_fallback_explanation(self, restaurant: Restaurant, request: RecommendationRequest) -> str:
        """Generate a grounded, factual explanation when operating in heuristic fallback mode."""
        cuisines_str = ", ".join(restaurant.cuisines[:3])
        loc_str = restaurant.area or restaurant.city.title()
        features_str = ""
        if "online_delivery" in restaurant.features:
            features_str = " with online ordering available"
        elif "table_booking" in restaurant.features:
            features_str = " with table reservations"

        explanation = (
            f"{restaurant.name} is a highly regarded {cuisines_str} spot in {loc_str}{features_str}. "
            f"It features a {restaurant.rating:.1f}★ rating with an estimated cost of ₹{restaurant.cost_for_two:,} for two."
        )
        return explanation

    def _generate_fallback_response(
        self,
        request: RecommendationRequest,
        filter_result: FilterResult,
        notice: str = "AI reasoning is temporarily running in offline heuristic fallback mode.",
    ) -> RecommendationResponse:
        """Construct deterministic recommendations when LLM generation fails or is unavailable."""
        target_count = min(request.top_n, len(filter_result.candidates))
        selected_candidates = filter_result.candidates[:target_count]

        items: list[RecommendationItem] = []
        for rank, candidate in enumerate(selected_candidates, start=1):
            raw_entity = filter_result.raw_restaurants[candidate.id]
            explanation = self._generate_fallback_explanation(raw_entity, request)

            highlights = [c for c in raw_entity.cuisines[:2]]
            if raw_entity.rating >= 4.5:
                highlights.append("Top Rated")
            if raw_entity.cost_for_two <= 500:
                highlights.append("Budget Friendly")

            item = RecommendationItem(
                rank=rank,
                id=raw_entity.id,
                name=raw_entity.name,
                city=raw_entity.city.title(),
                area=raw_entity.area,
                cuisine=raw_entity.cuisines,
                rating=raw_entity.rating,
                estimated_cost=raw_entity.cost_for_two,
                features=raw_entity.features,
                explanation=explanation,
                highlights=highlights[:3],
            )
            items.append(item)

        summary = (
            f"Top {len(items)} curated restaurant recommendations in {request.location} "
            f"ordered by highest customer ratings and value."
        )

        return RecommendationResponse(
            query_echo=request.model_dump(),
            count=len(items),
            recommendations=items,
            summary=summary,
            relaxation=filter_result.relaxation,
            ai_generated=False,
            fallback_notice=notice,
        )

    def _reconcile_and_hydrate(
        self,
        llm_output: LLMStructuredOutput,
        filter_result: FilterResult,
        request: RecommendationRequest,
    ) -> list[RecommendationItem]:
        """Reconcile LLM selections against candidate shortlist and hydrate factual metadata from database.

        Anti-Hallucination Rules:
            1. Every selected ID must exist in candidate shortlist; unknown IDs are purged.
            2. Duplicates from LLM output are deduplicated by appearance order.
            3. If fewer than requested items were selected, backfill from deterministic pre-ranking.
            4. Factual fields (name, rating, cost, cuisine, area) are always re-hydrated from database.
        """
        raw_map = filter_result.raw_restaurants
        valid_items: list[RecommendationItem] = []
        seen_ids: set[str] = set()

        # 1. Process and validate LLM selections
        for selected in llm_output.recommendations:
            rest_id = selected.id
            if rest_id not in raw_map:
                logger.warning("Purging hallucinated restaurant ID '%s' not present in shortlist.", rest_id)
                continue

            if rest_id in seen_ids:
                continue

            seen_ids.add(rest_id)
            raw_entity = raw_map[rest_id]

            item = RecommendationItem(
                rank=len(valid_items) + 1,
                id=raw_entity.id,
                name=raw_entity.name,
                city=raw_entity.city.title(),
                area=raw_entity.area,
                cuisine=raw_entity.cuisines,
                rating=raw_entity.rating,
                estimated_cost=raw_entity.cost_for_two,
                features=raw_entity.features,
                explanation=selected.explanation.strip(),
                highlights=selected.highlights if selected.highlights else raw_entity.cuisines[:2],
            )
            valid_items.append(item)

            if len(valid_items) >= request.top_n:
                break

        # 2. Backfill from deterministic shortlist if model under-selected
        if len(valid_items) < request.top_n:
            for candidate in filter_result.candidates:
                if len(valid_items) >= request.top_n:
                    break
                if candidate.id not in seen_ids:
                    seen_ids.add(candidate.id)
                    raw_entity = raw_map[candidate.id]
                    backfill_item = RecommendationItem(
                        rank=len(valid_items) + 1,
                        id=raw_entity.id,
                        name=raw_entity.name,
                        city=raw_entity.city.title(),
                        area=raw_entity.area,
                        cuisine=raw_entity.cuisines,
                        rating=raw_entity.rating,
                        estimated_cost=raw_entity.cost_for_two,
                        features=raw_entity.features,
                        explanation=self._generate_fallback_explanation(raw_entity, request),
                        highlights=raw_entity.cuisines[:2],
                    )
                    valid_items.append(backfill_item)

        # 3. Finalize rank indexing (1 to N)
        for idx, item in enumerate(valid_items, start=1):
            object.__setattr__(item, "rank", idx)

        return valid_items

    async def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        """Execute the end-to-end recommendation workflow.

        Workflow:
            1. Retrieve & Shortlist candidates with progressive relaxation.
            2. If 0 candidates, return graceful empty response.
            3. Build grounded prompt with candidate context.
            4. Invoke LLM provider (Groq) for ranking and personalization.
            5. Reconcile selections, eliminate hallucinations, and hydrate metadata.
            6. Fallback gracefully to deterministic recommendations if LLM fails.
        """
        # 0. Check cache for exact query hit to save LLM tokens and rate limits
        cached_response = self.cache.get(request)
        if cached_response:
            logger.info("Serving cached recommendation for location: %s", request.location)
            return cached_response

        # 1. Deterministic candidate retrieval & shortlisting
        filter_result = self.filter_service.filter_and_shortlist(
            request=request,
            shortlist_size=self.settings.shortlist_size,
        )

        # Handle zero candidates (e.g. unknown location)
        if not filter_result.candidates:
            logger.info("Returning empty response for query in location: %s", request.location)
            return RecommendationResponse(
                query_echo=request.model_dump(),
                count=0,
                recommendations=[],
                summary=f"No matching restaurants found in '{request.location}'. Please select a supported city.",
                relaxation=filter_result.relaxation,
                ai_generated=False,
            )

        # 2. Build prompt
        user_prompt = self.prompt_builder.build_user_prompt(
            request=request,
            candidates=filter_result.candidates,
            relaxation=filter_result.relaxation,
        )

        # 3. Call LLM for structured reasoning
        try:
            llm_output, telemetry = await self.llm_client.generate_structured(
                system_prompt=PromptBuilder.SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_schema=LLMStructuredOutput,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
                timeout_seconds=self.settings.llm_timeout_seconds,
            )

            logger.info(
                "LLM recommendation completed in %.2fms (%s / %s, tokens: %d)",
                telemetry.latency_ms,
                telemetry.provider,
                telemetry.model_name,
                telemetry.total_tokens,
            )

            # 4. Anti-hallucination validation and canonical metadata hydration
            recommendations = self._reconcile_and_hydrate(
                llm_output=llm_output,
                filter_result=filter_result,
                request=request,
            )

            # Fallback if reconciliation resulted in 0 items
            if not recommendations:
                logger.warning("Reconciliation yielded 0 items. Triggering heuristic fallback.")
                return self._generate_fallback_response(request, filter_result)

            summary = llm_output.summary.strip() or f"Top {len(recommendations)} personalized dining recommendations."

            final_response = RecommendationResponse(
                query_echo=request.model_dump(),
                count=len(recommendations),
                recommendations=recommendations,
                summary=summary,
                relaxation=filter_result.relaxation,
                ai_generated=True,
                fallback_notice=None,
            )

            # Store in cache
            self.cache.set(request, final_response)
            return final_response

        except Exception as e:
            logger.warning(
                "LLM completion failed (%s). Activating resilient heuristic fallback.",
                str(e),
                exc_info=True,
            )
            return self._generate_fallback_response(
                request=request,
                filter_result=filter_result,
                notice=f"AI service currently in offline fallback mode ({e.__class__.__name__}).",
            )
