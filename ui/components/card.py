"""Restaurant Recommendation Card Component for Obsidian Culinary AI."""

from app.models.recommendation import RecommendationItem
from ui.html_renderer import escape, render_html


def build_restaurant_card_html(item: RecommendationItem) -> str:
    """Build HTML for a single restaurant recommendation card."""
    loc_str = f"{item.area}, {item.city}" if item.area else item.city

    base_match = max(80.0, min(99.4, 95.0 + (item.rating - 4.0) * 8.0 - (item.rank - 1) * 2.2))
    match_pct = f"{base_match:.1f}%"

    cuisines_html = "".join(
        f'<span class="pill-cuisine">{escape(c)}</span>' for c in item.cuisine
    )

    features_html = ""
    if "online_delivery" in item.features:
        features_html += '<span class="pill-feature">🛵 Online Delivery</span>'
    if "table_booking" in item.features:
        features_html += '<span class="pill-feature">📅 Table Booking</span>'
    for feature in item.features:
        if feature not in {"online_delivery", "table_booking"}:
            features_html += (
                f'<span class="pill-feature">{escape(feature.replace("_", " ").title())}</span>'
            )

    highlights_html = "".join(
        f'<span class="pill-highlight">✨ {escape(h)}</span>' for h in item.highlights
    )

    if item.estimated_cost <= 500:
        budget_label = "LOW"
    elif item.estimated_cost <= 1200:
        budget_label = "MEDIUM"
    else:
        budget_label = "HIGH"

    return (
        '<div class="restaurant-card">'
        '<div class="card-top-row">'
        '<div>'
        '<div>'
        f'<span class="rank-pill">#{item.rank}</span>'
        f'<span class="restaurant-title">{escape(item.name)}</span>'
        '</div>'
        f'<div class="restaurant-location">📍 {escape(loc_str)}</div>'
        '</div>'
        '<div style="text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 6px;">'
        f'<span class="rating-badge">★ {item.rating:.1f}</span>'
        f'<span class="cost-badge">₹{item.estimated_cost:,} for two • '
        f'<span style="color:#FF4D5A; font-weight:600;">{budget_label}</span></span>'
        '</div>'
        '</div>'
        '<div class="taste-match-container">'
        '<span class="match-label">Taste Match</span>'
        '<div class="match-progress-bar">'
        f'<div class="match-progress-fill" style="width: {match_pct};"></div>'
        '</div>'
        f'<span class="match-score">{match_pct}</span>'
        '</div>'
        f'<div style="margin-top: 12px;">{cuisines_html}</div>'
        f'<div style="margin-top: 6px;">{features_html} {highlights_html}</div>'
        '<div class="ai-reasoning-panel">'
        '<div class="ai-reasoning-header">'
        '<span>🤖</span>'
        '<span>Neural Reasoning & Context Grounding</span>'
        '</div>'
        f'<div class="ai-reasoning-body">{escape(item.explanation)}</div>'
        '</div>'
        '</div>'
    )


def render_restaurant_card(item: RecommendationItem, total_results: int = 5) -> str:
    """Backward-compatible alias that returns card HTML."""
    _ = total_results
    return build_restaurant_card_html(item)


def render_restaurant_cards(items: list[RecommendationItem], *, render_key: str = "results") -> None:
    """Render all recommendation cards in one styled HTML block."""
    if not items:
        return
    cards_html = "".join(build_restaurant_card_html(item) for item in items)
    render_html(
        f'<div class="results-feed" id="{render_key}">{cards_html}</div>',
        key=render_key,
    )
