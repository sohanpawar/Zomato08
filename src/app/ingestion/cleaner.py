"""Data Cleaning, Normalization, and Entity Transformation Module.

Handles raw field parsing, type coercion, budget bucket classification,
feature extraction, deterministic ID generation, and record deduplication
for the Zomato restaurant dataset.
"""

import hashlib
import re
from typing import Any

from app.logging import get_logger
from app.models.restaurant import BudgetBucket, Restaurant

logger = get_logger(__name__)


# Regular expression for matching floating point ratings like "4.1/5", "3.8 / 5", "4.0", "3,8"
RATING_PATTERN = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:/\s*5)?", re.IGNORECASE)

# Regular expression to extract digits from cost strings like "1,200", "₹800", "Rs. 450"
DIGIT_PATTERN = re.compile(r"\d+")


def parse_rating(raw_rate: Any) -> float | None:
    """Parse raw rating into a normalized float between 0.0 and 5.0.

    Handles:
        - "4.1/5", "4.1 / 5", "4.1" -> 4.1
        - "3,8" (comma decimal) -> 3.8
        - "NEW", "-", "", None -> None
        - Out-of-bounds (> 5.0 or < 0.0) -> None
    """
    if raw_rate is None:
        return None

    str_val = str(raw_rate).strip()
    if not str_val or str_val.upper() in {"NEW", "-", "NONE", "NAN", "NULL"}:
        return None

    # Replace comma decimal with dot
    str_val = str_val.replace(",", ".")

    match = RATING_PATTERN.match(str_val)
    if not match:
        return None

    try:
        val = float(match.group(1))
        if 0.0 <= val <= 5.0:
            return round(val, 2)
        return None
    except (ValueError, TypeError):
        return None


def parse_cost(raw_cost: Any) -> int | None:
    """Parse raw cost for two into a positive integer.

    Handles:
        - "1,200", "1 200" -> 1200
        - "₹800", "Rs. 800", "INR 800" -> 800
        - 500, 500.0 -> 500
        - "0", "-100", None, "" -> None (or invalid)
    """
    if raw_cost is None:
        return None

    str_val = str(raw_cost).strip()
    if not str_val or str_val.upper() in {"NONE", "NAN", "NULL", "-"}:
        return None

    # Find all contiguous digit sequences
    digits = "".join(DIGIT_PATTERN.findall(str_val))
    if not digits:
        return None

    try:
        cost = int(digits)
        # Filter out 0 or unrealistic negative / extreme costs
        if cost > 0:
            return cost
        return None
    except (ValueError, TypeError):
        return None


def parse_cuisines(raw_cuisines: Any) -> list[str]:
    """Parse raw cuisine string into a normalized list of cuisines.

    Handles:
        - "North Indian, Chinese, Continental" -> ["North Indian", "Chinese", "Continental"]
        - Mixed delimiters (";", "/", "|") -> normalized by comma
        - Trailing spaces and casing -> title-cased and trimmed
        - Empty or None -> []
    """
    if raw_cuisines is None:
        return []

    str_val = str(raw_cuisines).strip()
    if not str_val or str_val.upper() in {"NONE", "NAN", "NULL", "-"}:
        return []

    # Normalize delimiters to commas
    normalized = str_val.replace(";", ",").replace("/", ",").replace("|", ",")
    raw_tokens = [token.strip() for token in normalized.split(",") if token.strip()]

    # Standardize casing (Title Case) while preserving unique entries
    cuisines: list[str] = []
    seen: set[str] = set()

    for token in raw_tokens:
        # Title case standard cuisine names
        norm_token = " ".join(word.capitalize() for word in token.split())
        key = norm_token.lower()
        if key not in seen and len(norm_token) > 1:
            seen.add(key)
            cuisines.append(norm_token)

    return cuisines


def derive_budget_bucket(cost_for_two: int) -> BudgetBucket:
    """Derive categorical budget tier from estimated cost for two in INR.

    Tiers:
        - LOW:    cost <= 500
        - MEDIUM: 500 < cost <= 1200
        - HIGH:   cost > 1200
    """
    if cost_for_two <= 500:
        return BudgetBucket.LOW
    elif cost_for_two <= 1200:
        return BudgetBucket.MEDIUM
    else:
        return BudgetBucket.HIGH


def extract_features(raw_row: dict[str, Any]) -> list[str]:
    """Extract distinct feature tags from raw dataset attributes.

    Extracts:
        - online_order == "Yes" -> "online_delivery"
        - book_table == "Yes" -> "table_booking"
        - rest_type (e.g. "Casual Dining", "Cafe", "Pub") -> normalized slug tags
        - listed_in(type) (e.g. "Buffet", "Delivery", "Desserts") -> tags
    """
    features: list[str] = []
    seen: set[str] = set()

    def add_feature(tag: str) -> None:
        clean_tag = tag.strip().lower().replace(" ", "_").replace("-", "_")
        if clean_tag and clean_tag not in seen:
            seen.add(clean_tag)
            features.append(clean_tag)

    # Online order availability
    online_order = str(raw_row.get("online_order", "")).strip().lower()
    if online_order in {"yes", "true", "1"}:
        add_feature("online_delivery")

    # Table booking availability
    book_table = str(raw_row.get("book_table", "")).strip().lower()
    if book_table in {"yes", "true", "1"}:
        add_feature("table_booking")

    # Restaurant type (e.g., "Casual Dining, Bar")
    rest_type = raw_row.get("rest_type")
    if rest_type and isinstance(rest_type, str):
        for part in rest_type.split(","):
            part_clean = part.strip()
            if part_clean and part_clean.lower() not in {"none", "nan"}:
                add_feature(part_clean)

    # Listed type (e.g., "Buffet", "Pubs and bars")
    listed_type = raw_row.get("listed_in(type)")
    if listed_type and isinstance(listed_type, str):
        part_clean = listed_type.strip()
        if part_clean and part_clean.lower() not in {"none", "nan"}:
            add_feature(part_clean)

    return features


def generate_restaurant_id(name: str, city: str, area: str | None, address: str | None) -> str:
    """Generate a deterministic, collision-resistant unique ID for a restaurant."""
    norm_name = name.strip().lower()
    norm_city = city.strip().lower()
    norm_area = (area or "").strip().lower()
    norm_addr = (address or "").strip().lower()

    identity_str = f"{norm_name}|{norm_city}|{norm_area}|{norm_addr}"
    hash_digest = hashlib.sha256(identity_str.encode("utf-8")).hexdigest()[:12]
    return f"rest_{hash_digest}"


def normalize_raw_record(
    raw_row: dict[str, Any],
    default_city: str = "bangalore",
) -> tuple[Restaurant | None, str | None]:
    """Transform a single raw Zomato dictionary record into a canonical Restaurant domain entity.

    Returns:
        tuple[Restaurant | None, str | None]: (Restaurant entity, drop_reason if dropped)
    """
    # 1. Name validation
    raw_name = raw_row.get("name")
    if not raw_name or not str(raw_name).strip():
        return None, "missing_name"
    name = str(raw_name).strip()

    # 2. Rating validation
    raw_rate = raw_row.get("rate")
    rating = parse_rating(raw_rate)
    if rating is None:
        return None, "invalid_or_missing_rating"

    # 3. Cost validation
    raw_cost = raw_row.get("approx_cost(for two people)") or raw_row.get("cost_for_two")
    cost_for_two = parse_cost(raw_cost)
    if cost_for_two is None:
        return None, "invalid_or_missing_cost"

    # 4. Cuisine validation
    raw_cuisines = raw_row.get("cuisines")
    cuisines = parse_cuisines(raw_cuisines)
    if not cuisines:
        return None, "missing_cuisines"

    # 5. Location and Area normalization
    # In the Zomato Bangalore HF dataset, 'location' contains the locality/area (e.g. "Koramangala 5th Block")
    raw_location = raw_row.get("location") or raw_row.get("area")
    raw_city = raw_row.get("city") or raw_row.get("listed_in(city)")

    city = default_city.lower()
    area = str(raw_location).strip() if raw_location and str(raw_location).strip() else None

    # If raw_city is explicitly specified and different from the area
    if raw_city and str(raw_city).strip().lower() not in {city, "none", "nan"}:
        # In the HF dataset, listed_in(city) represents exploration zones in Bangalore
        if not area:
            area = str(raw_city).strip()

    # 6. Votes normalization
    raw_votes = raw_row.get("votes", 0)
    try:
        votes = max(0, int(raw_votes))
    except (ValueError, TypeError):
        votes = 0

    # 7. Feature extraction & Address
    features = extract_features(raw_row)
    address = str(raw_row.get("address", "")).strip() or None

    # 8. Budget bucket
    budget_bucket = derive_budget_bucket(cost_for_two)

    # 9. Deterministic ID
    restaurant_id = generate_restaurant_id(name=name, city=city, area=area, address=address)

    try:
        restaurant = Restaurant(
            id=restaurant_id,
            name=name,
            city=city,
            area=area,
            cuisines=cuisines,
            cost_for_two=cost_for_two,
            budget_bucket=budget_bucket,
            rating=rating,
            votes=votes,
            features=features,
            address=address,
        )
        return restaurant, None
    except Exception as e:
        logger.debug("Record validation failed for %s: %s", name, str(e))
        return None, f"validation_error: {e}"


def deduplicate_restaurants(restaurants: list[Restaurant]) -> tuple[list[Restaurant], int]:
    """Deduplicate restaurants that appear across multiple zone listings in the dataset.

    Groups by (name.lower(), city.lower(), area.lower() or address.lower()).
    Keeps the record with highest votes, then highest rating.

    Returns:
        tuple[list[Restaurant], int]: (deduplicated restaurants, count of duplicates removed)
    """
    grouped: dict[str, list[Restaurant]] = {}

    for rest in restaurants:
        norm_name = rest.name.strip().lower()
        norm_city = rest.city.strip().lower()
        norm_loc = (rest.area or rest.address or "").strip().lower()

        key = f"{norm_name}|{norm_city}|{norm_loc}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(rest)

    deduped: list[Restaurant] = []
    duplicates_removed = 0

    for _key, group in grouped.items():
        if len(group) == 1:
            deduped.append(group[0])
        else:
            duplicates_removed += len(group) - 1
            # Sort by votes descending, rating descending
            best_record = max(group, key=lambda r: (r.votes, r.rating))
            deduped.append(best_record)

    # Sort final result by ID for deterministic output order
    deduped.sort(key=lambda r: r.id)
    return deduped, duplicates_removed
