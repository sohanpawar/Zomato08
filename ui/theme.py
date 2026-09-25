"""Obsidian Culinary AI — Design System & Theme Engine."""

# Color Palette Design Tokens
CANVAS_BG = "#0D1117"
SURFACE_PRIMARY = "#161B22"
SURFACE_ELEVATED = "#21262D"
SURFACE_CONTAINER_HIGH = "#262A31"
BORDER_COLOR = "#30363D"

PRIMARY_CRIMSON = "#E23744"
CORAL_FLARE = "#FF4D5A"
SURFACE_TINT = "#FFB3B1"
EMISSIVE_GLOW = "0 0 16px rgba(226, 55, 68, 0.35)"

EMERALD_GREEN = "#238636"
AMBER_WARNING = "#D29922"
ORANGE_ACCENT = "#F0883E"

TEXT_PRIMARY = "#F0F6FC"
TEXT_SECONDARY = "#C9D1D9"
TEXT_MUTED = "#8B949E"
TEXT_AI_STREAM = "#E6EDF3"

FONT_LINKS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
"""

# Styles injected into st.html iframes (cards, banners)
COMPONENT_CSS = f"""
    .obsidian-navbar {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 12px;
        padding: 16px 24px;
        background: {SURFACE_PRIMARY};
        border: 1px solid {BORDER_COLOR};
        border-radius: 12px;
        margin-bottom: 24px;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.65);
    }}
    .brand-title {{
        font-size: 1.6rem;
        font-weight: 800;
        color: {TEXT_PRIMARY};
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    .brand-highlight {{ color: {CORAL_FLARE}; }}
    .brand-subtitle {{
        font-size: 0.85rem;
        color: {TEXT_MUTED};
        margin-top: 3px;
    }}
    .telemetry-chip {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(35, 134, 54, 0.12);
        border: 1px solid rgba(35, 134, 54, 0.4);
        color: #7BDB80;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.78rem;
        font-weight: 500;
        padding: 4px 12px;
        border-radius: 9999px;
        white-space: nowrap;
    }}
    .telemetry-dot {{
        width: 7px;
        height: 7px;
        border-radius: 50%;
    }}
    .restaurant-card {{
        background-color: {SURFACE_PRIMARY};
        border: 1px solid {BORDER_COLOR};
        border-radius: 12px;
        padding: 22px;
        margin-bottom: 20px;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.65);
    }}
    .card-top-row {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 16px;
        margin-bottom: 12px;
    }}
    .rank-pill {{
        background: linear-gradient(135deg, {PRIMARY_CRIMSON} 0%, {CORAL_FLARE} 100%);
        color: #FFFFFF;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        font-size: 0.82rem;
        padding: 3px 10px;
        border-radius: 6px;
        display: inline-block;
        margin-right: 10px;
    }}
    .restaurant-title {{
        font-size: 1.35rem;
        font-weight: 700;
        color: {TEXT_PRIMARY};
        display: inline;
    }}
    .restaurant-location {{
        color: {TEXT_MUTED};
        font-size: 0.9rem;
        margin-top: 4px;
    }}
    .rating-badge {{
        background-color: rgba(35, 134, 54, 0.15);
        border: 1px solid {EMERALD_GREEN};
        color: #7BDB80;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 8px;
        font-size: 0.9rem;
        white-space: nowrap;
    }}
    .cost-badge {{
        background-color: {SURFACE_ELEVATED};
        border: 1px solid {BORDER_COLOR};
        color: {TEXT_SECONDARY};
        font-family: 'JetBrains Mono', monospace;
        font-weight: 500;
        padding: 4px 10px;
        border-radius: 8px;
        font-size: 0.85rem;
        white-space: nowrap;
    }}
    .taste-match-container {{
        display: flex;
        align-items: center;
        gap: 8px;
        background: rgba(22, 27, 34, 0.8);
        border: 1px solid {BORDER_COLOR};
        padding: 6px 12px;
        border-radius: 8px;
        margin-top: 10px;
    }}
    .match-label {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        color: {TEXT_MUTED};
        text-transform: uppercase;
        letter-spacing: 0.05em;
        white-space: nowrap;
    }}
    .match-progress-bar {{
        flex-grow: 1;
        height: 6px;
        background: {SURFACE_ELEVATED};
        border-radius: 3px;
        overflow: hidden;
        min-width: 80px;
    }}
    .match-progress-fill {{
        height: 100%;
        background: linear-gradient(90deg, {PRIMARY_CRIMSON} 0%, {CORAL_FLARE} 100%);
        border-radius: 3px;
    }}
    .match-score {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.82rem;
        font-weight: 700;
        color: {CORAL_FLARE};
        white-space: nowrap;
    }}
    .pill-cuisine {{
        background-color: rgba(255, 83, 90, 0.12);
        border: 1px solid rgba(255, 83, 90, 0.35);
        color: {SURFACE_TINT};
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        font-weight: 500;
        padding: 3px 10px;
        border-radius: 9999px;
        margin-right: 6px;
        display: inline-block;
        margin-top: 6px;
    }}
    .pill-feature {{
        background-color: {SURFACE_ELEVATED};
        border: 1px solid {BORDER_COLOR};
        color: {TEXT_SECONDARY};
        font-size: 0.76rem;
        padding: 3px 9px;
        border-radius: 9999px;
        margin-right: 5px;
        display: inline-block;
        margin-top: 6px;
    }}
    .pill-highlight {{
        background-color: rgba(56, 189, 248, 0.1);
        border: 1px solid rgba(56, 189, 248, 0.3);
        color: #7DD3FC;
        font-size: 0.75rem;
        padding: 3px 9px;
        border-radius: 9999px;
        margin-right: 5px;
        display: inline-block;
        margin-top: 6px;
    }}
    .ai-reasoning-panel {{
        background: rgba(13, 17, 23, 0.85);
        border-left: 3px solid {PRIMARY_CRIMSON};
        border-top: 1px solid {BORDER_COLOR};
        border-right: 1px solid {BORDER_COLOR};
        border-bottom: 1px solid {BORDER_COLOR};
        border-radius: 0 8px 8px 0;
        padding: 14px 18px;
        margin-top: 16px;
    }}
    .ai-reasoning-header {{
        display: flex;
        align-items: center;
        gap: 6px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        font-weight: 600;
        color: {CORAL_FLARE};
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 6px;
    }}
    .ai-reasoning-body {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.85rem;
        color: {TEXT_AI_STREAM};
        line-height: 1.55;
    }}
    .summary-banner {{
        background: {SURFACE_PRIMARY};
        border-left: 4px solid {CORAL_FLARE};
        border: 1px solid {BORDER_COLOR};
        border-left: 4px solid {CORAL_FLARE};
        border-radius: 0 10px 10px 0;
        padding: 16px 20px;
        margin-bottom: 24px;
        color: {TEXT_PRIMARY};
    }}
    .relaxation-banner {{
        background: rgba(210, 153, 34, 0.1);
        border: 1px solid {AMBER_WARNING};
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 24px;
        color: #F0E6D2;
    }}
    .relaxation-list {{
        margin: 8px 0 0 0;
        padding-left: 20px;
        color: #E2D0A6;
        font-size: 0.88rem;
        font-family: 'JetBrains Mono', monospace;
    }}
    .fallback-banner {{
        background: rgba(33, 38, 45, 0.9);
        border: 1px solid {BORDER_COLOR};
        border-left: 4px solid {TEXT_MUTED};
        border-radius: 0 8px 8px 0;
        padding: 12px 16px;
        margin-bottom: 20px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.82rem;
        color: {TEXT_SECONDARY};
    }}
    .empty-state {{
        background: {SURFACE_PRIMARY};
        border: 1px solid {BORDER_COLOR};
        border-radius: 12px;
        padding: 32px 24px;
        text-align: center;
        margin-top: 20px;
    }}
"""

STREAMLIT_OVERRIDES_CSS = f"""
<style>
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    header[data-testid="stHeader"] {{
        background: transparent !important;
        border-bottom: none !important;
    }}
    [data-testid="stToolbar"] {{display: none;}}

    html, body, [data-testid="stAppViewContainer"], .main {{
        background-color: {CANVAS_BG} !important;
        color: {TEXT_SECONDARY} !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }}

    [data-testid="stAppViewContainer"] > .main {{
        background-color: {CANVAS_BG} !important;
    }}

    .block-container {{
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1100px;
    }}

    [data-testid="stSidebar"] {{
        background-color: {SURFACE_PRIMARY} !important;
        border-right: 1px solid {BORDER_COLOR} !important;
    }}

    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {{
        color: {TEXT_PRIMARY} !important;
    }}

    [data-testid="stSidebar"] .stButton > button {{
        background-color: {SURFACE_ELEVATED} !important;
        color: {TEXT_PRIMARY} !important;
        border: 1px solid {BORDER_COLOR} !important;
        box-shadow: none !important;
        font-size: 0.85rem !important;
        text-align: left !important;
    }}

    [data-testid="stSidebar"] .stButton > button:hover {{
        background-color: {SURFACE_CONTAINER_HIGH} !important;
        border-color: {CORAL_FLARE} !important;
        color: {TEXT_PRIMARY} !important;
    }}

    h1, h2, h3, h4, h5, h6 {{
        color: {TEXT_PRIMARY} !important;
        font-family: 'Inter', sans-serif !important;
    }}

    [data-testid="stWidgetLabel"] label,
    [data-testid="stWidgetLabel"] p {{
        color: {TEXT_SECONDARY} !important;
        font-weight: 500 !important;
    }}

    [data-testid="stCaptionContainer"] {{
        color: {TEXT_MUTED} !important;
    }}

    .stTextInput > div > div > input,
    .stSelectbox > div > div,
    .stMultiSelect > div > div,
    div[data-baseweb="select"] > div,
    div[data-baseweb="input"] > div {{
        background-color: {CANVAS_BG} !important;
        border-color: {BORDER_COLOR} !important;
        color: {TEXT_PRIMARY} !important;
        border-radius: 8px !important;
    }}

    .stTextInput > div > div > input:focus,
    .stSelectbox > div > div:focus-within,
    .stMultiSelect > div > div:focus-within {{
        border-color: {PRIMARY_CRIMSON} !important;
        box-shadow: 0 0 0 2px rgba(226, 55, 68, 0.25) !important;
    }}

    [data-baseweb="tag"] {{
        background: rgba(226, 55, 68, 0.18) !important;
        color: {SURFACE_TINT} !important;
        border: 1px solid rgba(255, 83, 90, 0.35) !important;
    }}

    .stSlider [data-testid="stThumbValue"] {{
        color: {CORAL_FLARE} !important;
        font-family: 'JetBrains Mono', monospace !important;
    }}

    div[data-testid="stExpander"] {{
        background: {SURFACE_PRIMARY} !important;
        border: 1px solid {BORDER_COLOR} !important;
        border-radius: 12px !important;
        overflow: hidden;
    }}

    div[data-testid="stExpander"] details summary {{
        background: {SURFACE_PRIMARY} !important;
        color: {TEXT_PRIMARY} !important;
    }}

    div[data-testid="stExpander"] details summary:hover {{
        color: {CORAL_FLARE} !important;
    }}

    div[data-testid="stExpanderDetails"] {{
        background: {SURFACE_PRIMARY} !important;
        border-top: 1px solid {BORDER_COLOR} !important;
        padding-top: 0.5rem;
    }}

    .stButton > button[kind="primary"],
    .stButton > button {{
        background-color: {PRIMARY_CRIMSON} !important;
        color: {TEXT_PRIMARY} !important;
        border: 1px solid {CORAL_FLARE} !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        box-shadow: {EMISSIVE_GLOW} !important;
    }}

    .stButton > button:hover {{
        background-color: {CORAL_FLARE} !important;
        border-color: {CORAL_FLARE} !important;
    }}

    hr {{
        border-color: {BORDER_COLOR} !important;
        margin: 1.5rem 0 !important;
    }}

    [data-testid="stAlert"] {{
        background: rgba(226, 55, 68, 0.12) !important;
        border: 1px solid rgba(226, 55, 68, 0.35) !important;
        color: {TEXT_PRIMARY} !important;
    }}

    [data-testid="stHtml"] iframe {{
        border: none !important;
        background: transparent !important;
    }}

    {COMPONENT_CSS}
</style>
"""

OBSIDIAN_THEME_CSS = FONT_LINKS + STREAMLIT_OVERRIDES_CSS
