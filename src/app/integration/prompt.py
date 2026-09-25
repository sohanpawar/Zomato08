"""Grounded LLM Prompt Construction Module.

Builds structured, injection-resistant system instructions and candidate-grounded user prompts
for LLM-based ranking, personalization, and explanation generation.
"""

import json
import re
from typing import Any

from app.models.recommendation import RecommendationRequest, RelaxationDetails
from app.models.restaurant import RestaurantCandidate


# Regex to sanitize adversarial prompt injection delimiters
DELIMITER_CLEAN_PATTERN = re.compile(r"[{}\[\]<|>]")


def sanitize_text(text: str, max_length: int = 200) -> str:
    """Sanitize user free-text input to mitigate prompt injection and template breakout.

    Args:
        text: Raw user preference string.
        max_length: Maximum allowed character length.

    Returns:
        Cleaned, bounded string treated purely as passive data.
    """
    if not text:
        return ""
    # Strip dangerous format tags and control chars
    cleaned = DELIMITER_CLEAN_PATTERN.sub("", text)
    cleaned = " ".join(cleaned.split())
    return cleaned[:max_length]


class PromptBuilder:
    """Builds grounded, structured prompts for the recommendation engine."""

    SYSTEM_PROMPT = """You are an expert AI restaurant recommendation advisor inspired by Zomato.
Your task is to review candidate restaurants, rank the best matches for the user's preferences, and provide personalized, compelling 1-2 sentence explanations.

CRITICAL OPERATIONAL RULES:
1. Grounding & Zero Hallucination:
   - You must select and rank restaurants ONLY from the provided candidate list below.
   - Match restaurants strictly by their unique "id".
   - NEVER invent, hallucinate, or reference any restaurant not present in the candidate list.
   - Base every explanation strictly on the candidate's actual attributes (cuisine, rating, cost, neighborhood/area, and features).
2. Ranking Logic:
   - Rank candidates that best satisfy the user's location, cuisine desires, budget comfort, and special preferences at the top.
   - Distinct, non-repetitive selections (do not recommend the same restaurant ID twice).
3. Output Format:
   - You must respond with valid, parseable JSON conforming strictly to the requested schema:
     {
       "recommendations": [
         {
           "id": "<exact candidate id>",
           "rank": 1,
           "explanation": "<1-2 concise, grounded sentences explaining why this fits the user's preferences>",
           "highlights": ["<short tag 1>", "<short tag 2>"]
         }
       ],
       "summary": "<crisp 1-2 sentence overall summary of the recommendations>"
     }
"""

    def build_user_prompt(
        self,
        request: RecommendationRequest,
        candidates: list[RestaurantCandidate],
        relaxation: RelaxationDetails | None = None,
    ) -> str:
        """Construct user prompt containing sanitized user preferences and serialized candidate list.

        Args:
            request: User recommendation criteria.
            candidates: Grounded shortlist of candidate restaurants.
            relaxation: Optional relaxation audit if initial criteria were relaxed.

        Returns:
            Formatted user prompt string.
        """
        # 1. Format user preferences
        cuisines_str = ", ".join(request.cuisine) if request.cuisine else "Any cuisine"
        budget_str = request.budget.value.upper()
        min_rating_str = f"{request.min_rating}★ or higher" if request.min_rating > 0 else "Any rating"

        sanitized_prefs: list[str] = []
        if request.preferences:
            for p in request.preferences:
                clean_p = sanitize_text(p)
                if clean_p:
                    sanitized_prefs.append(clean_p)
        preferences_str = ", ".join(sanitized_prefs) if sanitized_prefs else "None specified"

        # 2. Relaxation notices if applicable
        relaxation_section = ""
        if relaxation and relaxation.is_relaxed and relaxation.relaxation_applied:
            notices = "\n".join(f"  • {item}" for item in relaxation.relaxation_applied)
            relaxation_section = f"""
NOTE - Constraint Relaxation Applied:
The user's original criteria had few direct matches, so criteria were widened:
{notices}
"""

        # 3. Format candidate restaurants JSON
        candidates_data = [c.to_llm_dict() for c in candidates]
        candidates_json = json.dumps(candidates_data, indent=2)

        # 4. Assemble final prompt
        user_prompt = f"""<user_request>
Target Location: {request.location}
Budget Tier: {budget_str}
Preferred Cuisines: {cuisines_str}
Minimum Rating: {min_rating_str}
Special Preferences: {preferences_str}
Requested Top Recommendations: {request.top_n}
</user_request>
{relaxation_section}
<candidate_restaurants>
Total candidate pool provided: {len(candidates)}
{candidates_json}
</candidate_restaurants>

TASK:
1. Select the top {request.top_n} restaurants from the candidate list that best match the user's request.
2. For each selection, use its exact "id" and provide a 1-2 sentence personalized explanation grounded in its real fields.
3. Provide a concise overall summary of the recommendation set.
4. Output valid JSON strictly matching the schema.
"""
        return user_prompt
