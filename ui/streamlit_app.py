"""Obsidian Culinary AI — Frontend Application Entry Point.

Modular, component-based Streamlit frontend adhering to the Obsidian dark theme
design specification (docs/DESIGN.md) for AI-powered restaurant discovery.
"""

import os
import sys
from pathlib import Path
from typing import Any

import streamlit as st

# Setup system path for standalone execution
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))
sys.path.insert(0, str(root_dir))

from app.models.recommendation import RecommendationRequest
from app.models.restaurant import BudgetBucket
from ui.api_client import BackendAPIClient
from ui.components import (
    render_empty_state,
    render_error_banner,
    render_fallback_banner,
    render_filter_panel,
    render_header,
    render_relaxation_banner,
    render_restaurant_cards,
    render_sidebar,
    render_summary_banner,
)
from ui.theme import OBSIDIAN_THEME_CSS

# ==============================================================================
# 1. Page Configuration & Dark Theme Engine
# ==============================================================================

st.set_page_config(
    page_title="Obsidian Culinary AI — Restaurant Discovery",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(OBSIDIAN_THEME_CSS, unsafe_allow_html=True)


# ==============================================================================
# 2. State Initialization & API Client
# ==============================================================================

if "api_client" not in st.session_state:
    backend_url = os.getenv("BACKEND_API_URL", "http://localhost:8000")
    st.session_state.api_client = BackendAPIClient(base_url=backend_url)

api_client: BackendAPIClient = st.session_state.api_client

if "form_state" not in st.session_state:
    st.session_state.form_state = {
        "location": "Bangalore",
        "budget": "any",
        "cuisines": [],
        "min_rating": 4.0,
        "preferences": [],
        "custom_notes": "",
        "top_n": 5,
        "expanded": True,
    }

if "recommendations_result" not in st.session_state:
    st.session_state.recommendations_result = None

if "error_message" not in st.session_state:
    st.session_state.error_message = None

if "form_revision" not in st.session_state:
    st.session_state.form_revision = 0

if "results_revision" not in st.session_state:
    st.session_state.results_revision = 0


# ==============================================================================
# 3. Callbacks & Event Handlers
# ==============================================================================

def handle_preset(preset_data: dict[str, Any]) -> None:
    """Hydrates form state from a selected preset and triggers recommendation."""
    st.session_state.form_state.update(preset_data)
    st.session_state.form_state["expanded"] = False
    st.session_state.recommendations_result = None
    st.session_state.error_message = None

    # Execute search immediately for instant feedback
    combined_prefs = list(preset_data.get("preferences", []))
    if preset_data.get("custom_notes"):
        combined_prefs.append(preset_data["custom_notes"])

    req = RecommendationRequest(
        location=preset_data["location"],
        budget=BudgetBucket(preset_data.get("budget", "any")),
        cuisine=preset_data.get("cuisines") or None,
        min_rating=preset_data.get("min_rating", 4.0),
        preferences=combined_prefs or None,
        top_n=preset_data.get("top_n", 3),
    )

    with st.spinner("🤖 Consulting Groq AI & shortlisting top matches..."):
        result, error = api_client.get_recommendations(req)
        st.session_state.recommendations_result = result
        st.session_state.error_message = error
        st.session_state.form_revision += 1
        st.session_state.results_revision += 1
    st.rerun()


def handle_reset() -> None:
    """Resets all filter criteria and clear results."""
    st.session_state.form_state = {
        "location": "Bangalore",
        "budget": "any",
        "cuisines": [],
        "min_rating": 4.0,
        "preferences": [],
        "custom_notes": "",
        "top_n": 5,
        "expanded": True,
    }
    st.session_state.recommendations_result = None
    st.session_state.error_message = None
    st.session_state.form_revision += 1
    st.rerun()


def handle_submit(form_data: dict[str, Any]) -> None:
    """Processes user submission and queries the backend API."""
    loc = form_data.get("location", "").strip()
    if not loc:
        st.error("Please provide a valid location or neighborhood.")
        return

    st.session_state.form_state.update(form_data)
    st.session_state.form_state["expanded"] = False

    combined_prefs = list(form_data.get("preferences", []))
    if form_data.get("custom_notes"):
        combined_prefs.append(form_data["custom_notes"])

    req = RecommendationRequest(
        location=loc,
        budget=BudgetBucket(form_data.get("budget", "any")),
        cuisine=form_data.get("cuisines") or None,
        min_rating=form_data.get("min_rating", 0.0),
        preferences=combined_prefs or None,
        top_n=form_data.get("top_n", 5),
    )

    with st.spinner("🤖 Consulting Groq AI & scoring candidates..."):
        result, error = api_client.get_recommendations(req)
        st.session_state.recommendations_result = result
        st.session_state.error_message = error
        st.session_state.results_revision += 1
    st.rerun()


# ==============================================================================
# 4. Render Layout & Components
# ==============================================================================

# Fetch health and metadata
health_data = api_client.check_health()
metadata = api_client.get_metadata()

# 1. Top Navigation Bar with Telemetry
render_header(health_data)

# 2. Sidebar with Presets & Controls
render_sidebar(
    health_data=health_data,
    on_preset_selected=handle_preset,
    on_reset=handle_reset,
)

# 3. Preference Filter Panel
render_filter_panel(
    metadata=metadata,
    default_values=st.session_state.form_state,
    form_revision=st.session_state.form_revision,
    on_submit=handle_submit,
)

# 4. Error Banners
if st.session_state.error_message:
    render_error_banner(st.session_state.error_message)

# 5. Recommendation Results
result = st.session_state.recommendations_result

if result:
    st.markdown("---")

    # Summary Banner
    render_summary_banner(result.summary)

    # Relaxation Notice
    if result.relaxation and result.relaxation.is_relaxed:
        render_relaxation_banner(result.relaxation.relaxation_applied)

    # Fallback Notice
    if not result.ai_generated and result.fallback_notice:
        render_fallback_banner(result.fallback_notice)

    # Empty State
    if result.count == 0:
        render_empty_state(st.session_state.form_state.get("location", "the selected area"))

    # Restaurant Cards (single styled block — avoids iframe CSS isolation)
    render_restaurant_cards(
        result.recommendations,
        render_key=f"results_{st.session_state.results_revision}",
    )
