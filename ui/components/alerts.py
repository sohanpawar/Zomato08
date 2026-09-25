"""Alert, Notice, and Empty State Components for Obsidian Culinary AI."""

from ui.html_renderer import escape, render_html


def render_summary_banner(summary_text: str) -> None:
    """Renders the AI curator natural language summary banner."""
    html = (
        '<div class="summary-banner">'
        '<div style="display:flex; align-items:center; gap:8px; font-family:\'JetBrains Mono\', monospace; '
        'font-size:0.8rem; font-weight:700; color:#FF4D5A; text-transform:uppercase; '
        'letter-spacing:0.05em; margin-bottom:6px;">'
        '<span>💡</span><span>Executive Culinary Summary</span>'
        '</div>'
        f'<div style="font-size:0.95rem; line-height:1.5; color:#F0F6FC;">{escape(summary_text)}</div>'
        '</div>'
    )
    render_html(html, height=120)


def render_relaxation_banner(steps: list[str]) -> None:
    """Renders a warning banner when search filters were automatically relaxed."""
    if not steps:
        return

    steps_html = "".join(f"<li>{escape(step)}</li>" for step in steps)
    html = (
        '<div class="relaxation-banner">'
        '<div style="display:flex; align-items:center; gap:8px; font-weight:700; color:#F0883E; font-size:0.92rem;">'
        '<span>⚠️</span><span>Intelligent Constraint Relaxation Applied</span>'
        '</div>'
        '<div style="font-size:0.88rem; margin-top:4px; color:#E4BEBC;">'
        'Strict filters matched fewer than target candidates. Search bounds were dynamically softened:'
        '</div>'
        f'<ul class="relaxation-list">{steps_html}</ul>'
        '</div>'
    )
    render_html(html, height=130 + len(steps) * 24)


def render_fallback_banner(fallback_notice: str) -> None:
    """Renders an info callout when deterministic fallback pre-ranking was used."""
    if not fallback_notice:
        return

    html = (
        '<div class="fallback-banner">'
        f'ℹ️ {escape(fallback_notice)}'
        '</div>'
    )
    render_html(html, height=80)


def render_empty_state(location: str) -> None:
    """Renders an empty state view with actionable suggestions."""
    html = (
        '<div class="empty-state">'
        '<div style="font-size:2.5rem; margin-bottom:12px;">🔍</div>'
        f'<div style="font-size:1.2rem; font-weight:700; color:#F0F6FC; margin-bottom:8px;">'
        f'No Dining Matches Found in "{escape(location)}"'
        '</div>'
        '<div style="font-size:0.9rem; color:#8B949E; max-width:480px; margin:0 auto 18px auto; line-height:1.5;">'
        'We couldn\'t find restaurants meeting your exact combination of budget, cuisine, and rating constraints.'
        '</div>'
        '<div style="background:#0D1117; border:1px solid #30363D; border-radius:8px; padding:14px; '
        'max-width:420px; margin:0 auto; font-size:0.85rem; color:#C9D1D9; text-align:left;">'
        '<div style="font-weight:600; color:#FF4D5A; margin-bottom:6px;">Suggested Adjustments:</div>'
        '• Broaden budget tier to <b>Any Budget</b><br>'
        '• Lower minimum rating threshold (e.g. 3.5★)<br>'
        '• Try broader areas like <b>Bangalore</b>, <b>Koramangala</b>, or <b>Indiranagar</b>'
        '</div>'
        '</div>'
    )
    render_html(html, height=300)


def render_error_banner(error_message: str) -> None:
    """Renders a styled error banner for API failures."""
    html = (
        '<div class="relaxation-banner" style="border-color:#E23744; background:rgba(226,55,68,0.12);">'
        '<div style="font-weight:700; color:#FF4D5A; margin-bottom:6px;">Request Failed</div>'
        f'<div style="font-size:0.88rem; color:#F0F6FC; white-space:pre-wrap;">{escape(error_message)}</div>'
        '</div>'
    )
    render_html(html, height=140)
