"""Top Navigation & Brand Header Component for Obsidian Culinary AI."""

from typing import Any

from ui.html_renderer import escape, render_markdown_html


def render_header(health_data: dict[str, Any] | None = None) -> None:
    """Renders the top navigation bar with brand identity and live telemetry chip."""
    status_str = "offline"
    spots_count = 0
    model_str = "Groq (gpt-oss-120b)"

    if health_data:
        status_str = health_data.get("status", "unknown")
        spots_count = health_data.get("total_restaurants", 0)
        provider = health_data.get("llm_provider", "groq")
        model = health_data.get("llm_model", "openai/gpt-oss-120b")
        model_str = f"{provider.title()} ({model.split('/')[-1]})"

    is_connected = status_str == "healthy"
    dot_color = "#2EA043" if is_connected else "#D29922"
    status_text = (
        f"AI Engine Active • {spots_count:,} Spots • {model_str}"
        if is_connected
        else f"Backend {status_str.title()}"
    )

    navbar_html = (
        '<div class="obsidian-navbar">'
        '<div>'
        '<div class="brand-title">'
        '<span>🍽️</span>'
        '<span>Obsidian <span class="brand-highlight">Culinary AI</span></span>'
        '</div>'
        '<div class="brand-subtitle">'
        'Bangalore AI Restaurant Discovery Engine • Precision Data & Neural Reasoning'
        '</div>'
        '</div>'
        '<div class="telemetry-chip">'
        f'<span class="telemetry-dot" style="background: {dot_color}; box-shadow: 0 0 8px {dot_color};"></span>'
        f'<span>{escape(status_text)}</span>'
        '</div>'
        '</div>'
    )
    render_markdown_html(navbar_html)
