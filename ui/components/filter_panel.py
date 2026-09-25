"""Filter & Search Preferences Panel Component for Obsidian Culinary AI."""

from typing import Any, Callable

import streamlit as st

from app.models.recommendation import MetadataResponse
from ui.html_renderer import render_markdown_html


def render_filter_panel(
    metadata: MetadataResponse,
    default_values: dict[str, Any],
    on_submit: Callable[[dict[str, Any]], None],
    form_revision: int = 0,
) -> None:
    """Renders the comprehensive preference configuration panel with dark-mode styling."""
    all_cuisines = sorted(list(set(metadata.cuisines))) if metadata.cuisines else []

    with st.expander("🎛️ Preference Parameters", expanded=default_values.get("expanded", True)):
        render_markdown_html(
            '<p style="font-size:0.85rem; color:#8B949E; margin:0 0 14px 0;">'
            'Configure location, budget, cuisines, rating threshold, and vibe preferences.'
            '</p>'
        )

        col1, col2 = st.columns([1, 1], gap="medium")

        with col1:
            location_val = st.text_input(
                "Location",
                value=default_values.get("location", "Bangalore"),
                placeholder="e.g. Bangalore, Koramangala, Indiranagar",
                help="Enter a city or neighborhood.",
                key=f"input_loc_{form_revision}",
            )

            budget_options = ["any", "low", "medium", "high"]
            budget_map = {
                "any": "Any Budget",
                "low": "Low (< ₹500 for two)",
                "medium": "Medium (₹500 – ₹1,200)",
                "high": "High (> ₹1,200)",
            }
            cur_budget = default_values.get("budget", "any")
            budget_idx = budget_options.index(cur_budget) if cur_budget in budget_options else 0

            budget_val = st.selectbox(
                "Budget",
                options=budget_options,
                index=budget_idx,
                format_func=lambda x: budget_map.get(x, x),
                key=f"input_budget_{form_revision}",
            )

            min_rating_val = st.slider(
                "Minimum Rating",
                min_value=0.0,
                max_value=5.0,
                value=float(default_values.get("min_rating", 4.0)),
                step=0.1,
                format="%.1f★",
                key=f"input_rating_{form_revision}",
            )

        with col2:
            preselected_cuisines = [
                c for c in default_values.get("cuisines", []) if c in all_cuisines
            ]
            cuisines_val = st.multiselect(
                "Cuisines",
                options=all_cuisines,
                default=preselected_cuisines,
                placeholder="Italian, North Indian, Cafe...",
                key=f"input_cuisines_{form_revision}",
            )

            preset_tags = [
                "romantic ambiance",
                "table booking",
                "quick service",
                "budget friendly",
                "online delivery",
                "outdoor seating",
                "family friendly",
                "artisan coffee",
                "desserts lover",
            ]
            valid_tag_defaults = [
                t for t in default_values.get("preferences", []) if t in preset_tags
            ]

            preferences_val = st.multiselect(
                "Vibe & Features",
                options=preset_tags,
                default=valid_tag_defaults,
                placeholder="Select atmosphere tags",
                key=f"input_vibes_{form_revision}",
            )

            custom_notes_val = st.text_input(
                "Additional Notes",
                value=default_values.get("custom_notes", ""),
                placeholder="e.g. wood-fired pizza and craft mocktails",
                max_chars=200,
                key=f"input_notes_{form_revision}",
            )

        col_sub1, col_sub2 = st.columns([1, 2], gap="medium")
        with col_sub1:
            top_n_val = st.slider(
                "Results Count",
                min_value=1,
                max_value=10,
                value=int(default_values.get("top_n", 5)),
                step=1,
                key=f"input_top_n_{form_revision}",
            )

        with col_sub2:
            st.write("")
            st.write("")
            submit_clicked = st.button(
                "🚀 Get Recommendations",
                type="primary",
                use_container_width=True,
                key="btn_run_pipeline",
            )

        if submit_clicked:
            on_submit({
                "location": location_val.strip(),
                "budget": budget_val,
                "cuisines": cuisines_val,
                "min_rating": min_rating_val,
                "preferences": preferences_val,
                "custom_notes": custom_notes_val.strip(),
                "top_n": top_n_val,
            })
