"""Safe HTML rendering helpers for Streamlit components."""

from __future__ import annotations

import html as html_module

from ui.theme import COMPONENT_CSS, FONT_LINKS


def escape(text: str) -> str:
    """Escape dynamic text before embedding in HTML."""
    return html_module.escape(str(text))


def _wrap_document(html: str) -> str:
    return (
        f"{FONT_LINKS}"
        "<style>"
        "html, body { margin: 0; padding: 0; background: transparent; color: #C9D1D9; "
        "font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }"
        f"{COMPONENT_CSS}"
        "</style>"
        f"{html}"
    )


def render_html(html: str, *, height: int = 180, key: str | None = None) -> None:
    """Render styled HTML inline using the global Obsidian theme (no iframe overlay)."""
    import streamlit as st

    _ = height  # retained for call-site compatibility
    _ = key
    st.markdown(html, unsafe_allow_html=True)


def render_markdown_html(html: str) -> None:
    """Render HTML blocks that inherit global page CSS (navbar, inline notices)."""
    import streamlit as st

    st.markdown(html, unsafe_allow_html=True)
