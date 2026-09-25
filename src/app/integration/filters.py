"""Candidate Filtering, Pre-Ranking Scoring, and Progressive Constraint Relaxation.

Implements deterministic candidate retrieval from SQLite, transparent multi-factor
pre-ranking, and graceful multi-tier constraint relaxation when strict criteria yield
zero or insufficient candidate matches.
"""

from dataclasses import dataclass, field
from typing import Any

from app.data.repository import RestaurantRepository
from app.logging import get_logger
from app.models.recommendation import RecommendationRequest, RelaxationDetails
from app.models.restaurant import BudgetBucket, Restaurant, RestaurantCandidate

logger = get_logger(__name__)


@dataclass
class FilterResult:
    """Encapsulates the shortlisted candidates and relaxation audit metadata."""

    candidates: list[RestaurantCandidate] = field(default_factory=list)
    raw_restaurants: dict[str, Restaurant] = field(default_factory=dict)
    relaxation: RelaxationDetails | None = None
    total_matches_found: int = 0
    is_relaxed: bool = False


class CandidateFilterService:
    """Service for deterministic candidate filtering, scoring, and relaxation."""

    def __init__(self, repository: RestaurantRepository) -> None:
        self.repository = repository

    def calculate_pre_ranking_score(
        self,
        restaurant: Restaurant,
        request: RecommendationRequest,
    ) -> float:
        """Calculate a transparent, deterministic multi-factor relevance score.

        Score Components:
            - Rating Signal:         Rating * 1000 (e.g., 4.5 -> 4500)
            - Vote Confidence:       min(Votes, 500)
            - Value for Money:       1000 / (Cost + 1)
            - Multi-Cuisine Boost:   +200 for each matched requested cuisine
            - Feature Match Boost:   +150 for each matched user preference tag
            - Specific Area Boost:   +250 if user location matches restaurant's neighborhood area

        Formula:
            Score = (Rating * 1000) + min(Votes, 500) + (1000 / (Cost + 1)) + Boosts
        """
        # 1. Base rating and vote signals
        base_rating_score = restaurant.rating * 1000.0
        vote_confidence = min(float(restaurant.votes), 500.0)
        value_score = 1000.0 / (float(restaurant.cost_for_two) + 1.0)

        # 2. Cuisine match overlap boost
        cuisine_boost = 0.0
        if request.cuisine:
            req_cuisines_lower = {c.strip().lower() for c in request.cuisine if c.strip()}
            rest_cuisines_lower = {c.strip().lower() for c in restaurant.cuisines}
            matching_cuisines = req_cuisines_lower.intersection(rest_cuisines_lower)
            cuisine_boost = len(matching_cuisines) * 200.0

        # 3. Preference & feature match boost
        feature_boost = 0.0
        if request.preferences:
            req_prefs = {p.strip().lower().replace(" ", "_").replace("-", "_") for p in request.preferences if p.strip()}
            rest_feats = {f.strip().lower().replace(" ", "_").replace("-", "_") for f in restaurant.features}
            matching_features = req_prefs.intersection(rest_feats)
            feature_boost = len(matching_features) * 150.0

        # 4. Neighborhood / Area match boost
        area_boost = 0.0
        if restaurant.area and request.location.strip().lower() in restaurant.area.strip().lower():
            area_boost = 250.0

        total_score = (
            base_rating_score
            + vote_confidence
            + value_score
            + cuisine_boost
            + feature_boost
            + area_boost
        )

        return round(total_score, 4)

    def sort_and_rank_candidates(
        self,
        restaurants: list[Restaurant],
        request: RecommendationRequest,
    ) -> list[Restaurant]:
        """Sort candidate restaurants deterministically by calculated score and tie-breakers.

        Tie-breaking Order:
            1. Pre-ranking Score (DESC)
            2. Rating (DESC)
            3. Votes (DESC)
            4. Cost for Two (ASC)
            5. ID (ASC) -> Guarantees 100% deterministic ordering across runs
        """
        scored_pairs = [
            (self.calculate_pre_ranking_score(r, request), r)
            for r in restaurants
        ]

        scored_pairs.sort(
            key=lambda pair: (
                pair[0],                      # Calculated score
                pair[1].rating,               # Rating
                pair[1].votes,                # Votes
                -pair[1].cost_for_two,        # Lower cost preferred in ties
                pair[1].id,                   # Stable unique ID
            ),
            reverse=True,
        )

        return [pair[1] for pair in scored_pairs]

    def filter_and_shortlist(
        self,
        request: RecommendationRequest,
        shortlist_size: int = 20,
    ) -> FilterResult:
        """Retrieve, pre-rank, and shortlist candidate restaurants.

        If strict filtering produces fewer candidates than requested top_n,
        progressively relaxes constraints to find relevant alternatives.
        """
        k_limit = max(shortlist_size, request.top_n)

        # ----------------------------------------------------------------------
        # Step 0: Strict Query Execution
        # ----------------------------------------------------------------------
        strict_candidates = self.repository.find_candidates(
            location=request.location,
            budget=request.budget,
            cuisines=request.cuisine,
            min_rating=request.min_rating,
            limit=k_limit,
        )

        # If strict candidates satisfy top_n requirement, return immediately
        if len(strict_candidates) >= request.top_n:
            sorted_candidates = self.sort_and_rank_candidates(strict_candidates, request)[:k_limit]
            raw_map = {r.id: r for r in sorted_candidates}
            candidate_models = [RestaurantCandidate.from_restaurant(r) for r in sorted_candidates]

            return FilterResult(
                candidates=candidate_models,
                raw_restaurants=raw_map,
                relaxation=None,
                total_matches_found=len(strict_candidates),
                is_relaxed=False,
            )

        # ----------------------------------------------------------------------
        # Progressive Relaxation Pipeline
        # ----------------------------------------------------------------------
        logger.info(
            "Strict search yielded %d candidates for location '%s' (required: %d). Triggering constraint relaxation.",
            len(strict_candidates),
            request.location,
            request.top_n,
        )

        relaxation_steps: list[str] = []
        accumulated_candidates: dict[str, Restaurant] = {r.id: r for r in strict_candidates}

        # Stage 0: Neighborhood not in catalog — expand to city-wide search
        norm_loc = request.location.strip().lower()
        known_cities = {city.lower() for city in self.repository.list_cities()}
        if not accumulated_candidates and norm_loc not in known_cities:
            fallback_city: str | None = None
            for city in sorted(known_cities):
                city_candidates = self.repository.find_candidates(
                    location=city,
                    budget=request.budget,
                    cuisines=request.cuisine,
                    min_rating=request.min_rating,
                    limit=k_limit,
                )
                if city_candidates and fallback_city is None:
                    fallback_city = city
                for restaurant in city_candidates:
                    accumulated_candidates[restaurant.id] = restaurant

            if accumulated_candidates and fallback_city:
                relaxation_steps.append(
                    f"Expanded search area from '{request.location}' to city-wide {fallback_city.title()}"
                )

        original_rating = request.min_rating
        original_budget = request.budget
        original_cuisines = request.cuisine

        current_rating = original_rating
        current_budget = original_budget
        current_cuisines = original_cuisines

        # Stage 1: Lower minimum rating threshold in progressive decrements
        while current_rating > 3.0 and len(accumulated_candidates) < request.top_n:
            current_rating = max(0.0, round(current_rating - 0.5, 2))
            relaxed_batch = self.repository.find_candidates(
                location=request.location,
                budget=current_budget,
                cuisines=current_cuisines,
                min_rating=current_rating,
                limit=k_limit,
            )
            for r in relaxed_batch:
                accumulated_candidates[r.id] = r

        if current_rating < original_rating:
            relaxation_steps.append(
                f"Lowered minimum rating threshold from {original_rating}★ to {current_rating}★"
            )

        # Stage 2: Widen budget constraint to ANY
        if len(accumulated_candidates) < request.top_n and current_budget != BudgetBucket.ANY:
            current_budget = BudgetBucket.ANY
            relaxed_batch = self.repository.find_candidates(
                location=request.location,
                budget=current_budget,
                cuisines=current_cuisines,
                min_rating=current_rating,
                limit=k_limit,
            )
            for r in relaxed_batch:
                accumulated_candidates[r.id] = r

            step_msg = f"Expanded budget tier from '{request.budget.value}' to all price ranges"
            if step_msg not in relaxation_steps:
                relaxation_steps.append(step_msg)

        # Stage 3: Relax cuisine constraint (recommend top-rated restaurants in location)
        if len(accumulated_candidates) < request.top_n and current_cuisines is not None:
            current_cuisines = None
            relaxed_batch = self.repository.find_candidates(
                location=request.location,
                budget=current_budget,
                cuisines=current_cuisines,
                min_rating=current_rating,
                limit=k_limit,
            )
            for r in relaxed_batch:
                accumulated_candidates[r.id] = r

            step_msg = f"Broadened cuisine criteria to include popular dining options in {request.location}"
            if step_msg not in relaxation_steps:
                relaxation_steps.append(step_msg)

        # Stage 4: Drop rating constraint completely if still zero
        if len(accumulated_candidates) == 0 and current_rating > 0.0:
            current_rating = 0.0
            relaxed_batch = self.repository.find_candidates(
                location=request.location,
                budget=BudgetBucket.ANY,
                cuisines=None,
                min_rating=0.0,
                limit=k_limit,
            )
            for r in relaxed_batch:
                accumulated_candidates[r.id] = r

            if relaxed_batch:
                relaxation_steps.append("Removed minimum rating filter to show available restaurants")

        # ----------------------------------------------------------------------
        # Assemble Final Filtered Outcome
        # ----------------------------------------------------------------------
        combined_list = list(accumulated_candidates.values())

        if not combined_list:
            # Location has 0 restaurants in database
            logger.warning("Zero restaurants found in database for location: %s", request.location)
            return FilterResult(
                candidates=[],
                raw_restaurants={},
                relaxation=RelaxationDetails(
                    is_relaxed=True,
                    relaxation_applied=["No restaurants found in this location."],
                    effective_query={
                        "location": request.location,
                        "supported_cities": self.repository.list_cities(),
                    },
                ),
                total_matches_found=0,
                is_relaxed=True,
            )

        # Sort combined results deterministically
        sorted_all = self.sort_and_rank_candidates(combined_list, request)[:k_limit]
        raw_map = {r.id: r for r in sorted_all}
        candidate_models = [RestaurantCandidate.from_restaurant(r) for r in sorted_all]

        effective_query = {
            "location": request.location,
            "budget": current_budget.value,
            "cuisine": current_cuisines,
            "min_rating": current_rating,
        }

        constraints_changed = (
            current_rating != original_rating
            or current_budget != original_budget
            or current_cuisines != original_cuisines
        )

        relaxation_audit = None
        if constraints_changed and relaxation_steps:
            relaxation_audit = RelaxationDetails(
                is_relaxed=True,
                relaxation_applied=relaxation_steps,
                effective_query=effective_query,
            )

        return FilterResult(
            candidates=candidate_models,
            raw_restaurants=raw_map,
            relaxation=relaxation_audit,
            total_matches_found=len(combined_list),
            is_relaxed=relaxation_audit is not None,
        )
