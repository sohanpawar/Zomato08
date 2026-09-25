"""Sidebar Controls & Preset Journeys Component."""

from typing import Any, Callable

import streamlit as st

from ui.html_renderer import render_markdown_html


def render_sidebar(
    health_data: dict[str, Any],
    on_preset_selected: Callable[[dict[str, Any]], None],
    on_reset: Callable[[], None],
) -> None:
    """Renders the dark-theme sidebar with status, discovery presets, and reset action."""
    with st.sidebar:
        render_markdown_html(
            '<div style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">'
            '<span style="font-size:1.4rem;">🍷</span>'
            '<span style="font-size:1.1rem; font-weight:700; color:#F0F6FC;">Culinary Intelligence</span>'
            '</div>'
        )

        st.markdown("### ⚙️ Telemetry")
        status_str = health_data.get("status", "unknown")

        if status_str == "healthy":
            count = health_data.get("total_restaurants", 0)
            render_markdown_html(
                f'<div style="background:rgba(35, 134, 54, 0.12); border:1px solid rgba(35, 134, 54, 0.35); '
                f'border-radius:8px; padding:10px 14px; font-family:\'JetBrains Mono\', monospace; '
                f'font-size:0.8rem; color:#7BDB80;">'
                f'<div>● System Online</div>'
                f'<div style="color:#8B949E; font-size:0.75rem; margin-top:2px;">Catalog: {count:,} indexed venues</div>'
                f'</div>'
            )
        elif status_str == "degraded":
            st.warning("Backend online — database not populated yet.")
        else:
            st.error(f"Backend unreachable ({health_data.get('error', 'offline')})")

        st.markdown("---")
        st.markdown("### ⚡ Quick Discovery Presets")
        st.caption("One-click prompt journeys:")

        if st.button("🍝 Romantic Italian in Bangalore", use_container_width=True, key="preset_italian"):
            on_preset_selected({
                "location": "Bangalore",
                "budget": "high",
                "cuisines": ["Italian", "Continental"],
                "min_rating": 4.2,
                "preferences": ["romantic ambiance", "table booking"],
                "custom_notes": "candlelight dining and authentic wood-fired pizza",
                "top_n": 3,
            })

        if st.button("🍛 Budget South Indian in Jayanagar", use_container_width=True, key="preset_south"):
            on_preset_selected({
                "location": "Jayanagar",
                "budget": "low",
                "cuisines": ["South Indian", "Fast Food"],
                "min_rating": 4.0,
                "preferences": ["quick service", "budget friendly"],
                "custom_notes": "crispy masala dosa and authentic filter coffee",
                "top_n": 3,
            })

        if st.button("🍗 Mughlai Feast in Banashankari", use_container_width=True, key="preset_mughlai"):
            on_preset_selected({
                "location": "Banashankari",
                "budget": "medium",
                "cuisines": ["North Indian", "Mughlai", "Biryani"],
                "min_rating": 4.0,
                "preferences": ["family friendly", "online delivery"],
                "custom_notes": "rich butter chicken and aromatic dum biryani",
                "top_n": 4,
            })

        if st.button("☕ Cozy Specialty Cafe in Basavanagudi", use_container_width=True, key="preset_cafe"):
            on_preset_selected({
                "location": "Basavanagudi",
                "budget": "medium",
                "cuisines": ["Cafe", "Desserts", "Continental"],
                "min_rating": 4.0,
                "preferences": ["artisan coffee", "desserts lover"],
                "custom_notes": "great specialty roast coffee and artisan desserts",
                "top_n": 3,
            })

        st.markdown("---")
        if st.button("🔄 Reset Criteria", use_container_width=True, key="preset_reset"):
            on_reset()
