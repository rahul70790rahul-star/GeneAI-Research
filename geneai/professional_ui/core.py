"""Professional User Interface - Phase 5.8 Core."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Optional

import streamlit as st

logger = logging.getLogger(__name__)


class ThemeMode(Enum):
    """UI theme modes."""
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"
    HIGH_CONTRAST = "high_contrast"


class ColorScheme(Enum):
    """Predefined color schemes."""
    DEFAULT = "default"
    BLUE = "blue"
    GREEN = "green"
    PURPLE = "purple"
    ORANGE = "orange"
    RED = "red"
    TEAL = "teal"


def _coerce_mode(value: Any) -> ThemeMode:
    """Accept a :class:`ThemeMode` or its string value."""
    if isinstance(value, ThemeMode):
        return value
    if isinstance(value, str):
        try:
            return ThemeMode(value.strip().lower())
        except ValueError:
            pass
    return ThemeMode.LIGHT


def _coerce_scheme(value: Any) -> ColorScheme:
    """Accept a :class:`ColorScheme` or its string value."""
    if isinstance(value, ColorScheme):
        return value
    if isinstance(value, str):
        try:
            return ColorScheme(value.strip().lower())
        except ValueError:
            pass
    return ColorScheme.DEFAULT


@dataclass
class ThemeColors:
    """Color palette for a theme."""
    # Primary colors
    primary: str = "#1E88E5"
    primary_light: str = "#64B5F6"
    primary_dark: str = "#1565C0"
    
    # Secondary colors
    secondary: str = "#26A69A"
    secondary_light: str = "#80CBC4"
    secondary_dark: str = "#00897B"
    
    # Background colors
    background: str = "#FAFAFA"
    surface: str = "#FFFFFF"
    surface_variant: str = "#F5F5F5"
    
    # Text colors
    text_primary: str = "#212121"
    text_secondary: str = "#757575"
    text_disabled: str = "#BDBDBD"
    
    # Status colors
    success: str = "#4CAF50"
    warning: str = "#FF9800"
    error: str = "#F44336"
    info: str = "#2196F3"
    
    # Border/divider
    border: str = "#E0E0E0"
    divider: str = "#EEEEEE"
    
    # Chart colors
    chart_colors: list[str] = field(default_factory=lambda: [
        "#1E88E5", "#26A69A", "#FF9800", "#F44336", 
        "#9C27B0", "#00BCD4", "#8BC34A", "#FF5722"
    ])

    @property
    def text(self) -> str:
        """Primary text colour (short alias used by callers)."""
        return self.text_primary


@dataclass
class DarkThemeColors(ThemeColors):
    """Dark theme color palette."""
    primary: str = "#64B5F6"
    primary_light: str = "#90CAF9"
    primary_dark: str = "#42A5F5"
    
    secondary: str = "#80CBC4"
    secondary_light: str = "#B2DFDB"
    secondary_dark: str = "#4DB6AC"
    
    background: str = "#121212"
    surface: str = "#1E1E1E"
    surface_variant: str = "#2D2D2D"
    
    text_primary: str = "#FFFFFF"
    text_secondary: str = "#B0B0B0"
    text_disabled: str = "#757575"
    
    border: str = "#333333"
    divider: str = "#2D2D2D"


@dataclass
class HighContrastThemeColors(ThemeColors):
    """High contrast theme for accessibility."""
    primary: str = "#0066CC"
    primary_light: str = "#3399FF"
    primary_dark: str = "#004499"
    
    secondary: str = "#008888"
    secondary_light: str = "#00AAAA"
    secondary_dark: str = "#006666"
    
    background: str = "#FFFFFF"
    surface: str = "#FFFFFF"
    surface_variant: str = "#F0F0F0"
    
    text_primary: str = "#000000"
    text_secondary: str = "#333333"
    text_disabled: str = "#666666"
    
    success: str = "#006600"
    warning: str = "#CC6600"
    error: str = "#CC0000"
    info: str = "#0066CC"
    
    border: str = "#000000"
    divider: str = "#333333"


@dataclass
class ThemeConfig:
    """Complete theme configuration."""
    name: str = "Light"
    mode: ThemeMode = ThemeMode.LIGHT
    colors: ThemeColors | None = None
    color_scheme: ColorScheme = ColorScheme.DEFAULT
    font_size: str = "medium"
    compact_mode: bool = False
    animations: bool = True
    font_family: str = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    font_size_base: str = "14px"
    border_radius: str = "8px"
    border_radius_sm: str = "4px"
    border_radius_lg: str = "12px"
    spacing_unit: str = "8px"
    shadow_sm: str = "0 1px 2px rgba(0,0,0,0.05)"
    shadow_md: str = "0 4px 6px rgba(0,0,0,0.07)"
    shadow_lg: str = "0 10px 15px rgba(0,0,0,0.1)"
    transition: str = "all 0.2s ease"

    def __post_init__(self) -> None:
        self.mode = _coerce_mode(self.mode)
        self.color_scheme = _coerce_scheme(self.color_scheme)

    def resolved_colors(self) -> ThemeColors:
        """Return the palette for this configuration."""
        if self.colors is not None:
            return self.colors
        return THEMES.get(self.mode.value, THEMES["light"])

    def to_css_variables(self) -> str:
        """Generate CSS custom properties."""
        c = self.resolved_colors()
        font_sizes = {"small": "12px", "medium": "14px", "large": "16px"}
        base_size = font_sizes.get(self.font_size, self.font_size_base)
        return f"""
        :root {{
            --font-family: {self.font_family};
            --font-size-base: {base_size};
            --border-radius: {self.border_radius};
            --border-radius-sm: {self.border_radius_sm};
            --border-radius-lg: {self.border_radius_lg};
            --spacing-unit: {self.spacing_unit};
            --shadow-sm: {self.shadow_sm};
            --shadow-md: {self.shadow_md};
            --shadow-lg: {self.shadow_lg};
            --transition: {self.transition};

            --color-primary: {c.primary};
            --color-primary-light: {c.primary_light};
            --color-primary-dark: {c.primary_dark};
            --color-secondary: {c.secondary};
            --color-secondary-light: {c.secondary_light};
            --color-secondary-dark: {c.secondary_dark};
            --color-background: {c.background};
            --color-surface: {c.surface};
            --color-surface-variant: {c.surface_variant};
            --color-text-primary: {c.text_primary};
            --color-text-secondary: {c.text_secondary};
            --color-text-disabled: {c.text_disabled};
            --color-success: {c.success};
            --color-warning: {c.warning};
            --color-error: {c.error};
            --color-info: {c.info};
            --color-border: {c.border};
            --color-divider: {c.divider};
        }}
        """


# Predefined themes. Keyed by ``ThemeMode.value`` so callers can look them up
# with either strings ("light") or enum values (``mode.value``).
THEMES: dict[str, ThemeColors] = {
    "light": ThemeColors(),
    "dark": DarkThemeColors(),
    "auto": ThemeColors(),  # resolved via the CSS media query below
    "high_contrast": HighContrastThemeColors(),
}


# Color scheme variations
COLOR_SCHEMES: dict[str, dict[str, str]] = {
    "default": {"primary": "#1E88E5", "secondary": "#26A69A"},
    "blue": {"primary": "#1976D2", "secondary": "#0288D1"},
    "green": {"primary": "#388E3C", "secondary": "#009688"},
    "purple": {"primary": "#7B1FA2", "secondary": "#6A1B9A"},
    "orange": {"primary": "#F57C00", "secondary": "#E65100"},
    "red": {"primary": "#D32F2F", "secondary": "#C62828"},
    "teal": {"primary": "#00796B", "secondary": "#006064"},
}


def _normalise_theme_config(
    config: ThemeConfig | ThemeMode | str | None,
    color_scheme: ColorScheme | str | None,
) -> ThemeConfig:
    """Return a :class:`ThemeConfig` from the supported call shapes.

    ``ThemeConfig`` is the canonical form; passing a ``ThemeMode`` (and
    optionally a colour scheme) is kept for backwards compatibility.
    """
    if isinstance(config, ThemeConfig):
        result = config
        if color_scheme is not None:
            result = replace(result, color_scheme=_coerce_scheme(color_scheme))
        return result

    mode = _coerce_mode(config)
    scheme = _coerce_scheme(color_scheme)
    return ThemeConfig(
        name=mode.value.title(),
        mode=mode,
        colors=THEMES.get(mode.value, THEMES["light"]),
        color_scheme=scheme,
    )


def apply_theme(
    config: ThemeConfig | ThemeMode | str | None = None,
    color_scheme: ColorScheme | str | None = None,
) -> str:
    """Generate and inject theme CSS, returning the generated stylesheet."""
    theme = _normalise_theme_config(config, color_scheme)
    scheme = COLOR_SCHEMES.get(theme.color_scheme.value, COLOR_SCHEMES["default"])
    base_colors = theme.resolved_colors()

    colors = replace(
        base_colors,
        primary=scheme["primary"],
        primary_light=adjust_color(scheme["primary"], 1.3),
        primary_dark=adjust_color(scheme["primary"], 0.7),
        secondary=scheme["secondary"],
        secondary_light=adjust_color(scheme["secondary"], 1.3),
        secondary_dark=adjust_color(scheme["secondary"], 0.7),
    )
    css = replace(theme, colors=colors).to_css_variables()

    # Add dark mode media query for auto theme
    if theme.mode == ThemeMode.AUTO:
        dark_colors = replace(
            THEMES["dark"],
            primary=scheme["primary"],
            secondary=scheme["secondary"],
        )
        dark_css = ThemeConfig(
            name="Dark",
            mode=ThemeMode.DARK,
            colors=dark_colors,
            color_scheme=theme.color_scheme,
        ).to_css_variables()
        css += f"""
        @media (prefers-color-scheme: dark) {{
            {dark_css}
        }}
        """

    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    return css


def adjust_color(hex_color: str, factor: float) -> str:
    """Adjust color brightness.

    Invalid inputs are returned unchanged rather than raising, which keeps
    rendering resilient when a caller supplies a named CSS colour.
    """
    if not isinstance(hex_color, str):
        return hex_color
    value = hex_color.lstrip('#')
    if len(value) != 6:
        return hex_color
    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
    except ValueError:
        return hex_color

    r = min(255, max(0, int(r * factor)))
    g = min(255, max(0, int(g * factor)))
    b = min(255, max(0, int(b * factor)))

    return f"#{r:02x}{g:02x}{b:02x}"


def render_theme_selector() -> ThemeConfig:
    """Render the theme selector controls and return the chosen configuration."""
    with st.sidebar:
        st.subheader("🎨 Theme")

        mode_value = st.selectbox(
            "Mode",
            options=list(ThemeMode),
            format_func=lambda x: getattr(x, "value", str(x)).title(),
            index=0,
            key="theme_mode",
        )
        scheme_value = st.selectbox(
            "Color Scheme",
            options=list(ColorScheme),
            format_func=lambda x: getattr(x, "value", str(x)).title(),
            index=0,
            key="color_scheme",
        )
        compact = st.checkbox("Compact mode", value=False, key="compact_mode")
        animations = st.checkbox("Animations", value=True, key="animations")
        font_px = st.slider("Base font size (px)", 12, 20, 14, key="font_size")

    if font_px <= 12:
        font_size = "small"
    elif font_px >= 16:
        font_size = "large"
    else:
        font_size = "medium"

    config = ThemeConfig(
        mode=_coerce_mode(mode_value),
        color_scheme=_coerce_scheme(scheme_value),
        font_size=font_size,
        compact_mode=bool(compact),
        animations=bool(animations),
    )
    apply_theme(config)
    return config


# Custom CSS for professional UI
PROFESSIONAL_CSS = """
<style>
/* Global styles */
.stApp {
    font-family: var(--font-family);
    font-size: var(--font-size-base);
    background-color: var(--color-background);
    color: var(--color-text-primary);
}

/* Headers */
h1, h2, h3, h4, h5, h6 {
    color: var(--color-text-primary);
    font-weight: 600;
    line-height: 1.3;
}

h1 { font-size: 2.5rem; }
h2 { font-size: 2rem; }
h3 { font-size: 1.5rem; }

/* Cards */
.pro-card {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--border-radius);
    padding: calc(var(--spacing-unit) * 2);
    box-shadow: var(--shadow-sm);
    transition: var(--transition);
}

.pro-card:hover {
    box-shadow: var(--shadow-md);
    border-color: var(--color-primary-light);
}

/* Buttons */
.stButton > button {
    border-radius: var(--border-radius);
    font-weight: 500;
    padding: 0.5rem 1rem;
    transition: var(--transition);
    border: none;
}

.stButton > button[kind="primary"] {
    background: var(--color-primary);
    color: white;
}

.stButton > button[kind="primary"]:hover {
    background: var(--color-primary-dark);
    box-shadow: var(--shadow-md);
}

.stButton > button[kind="secondary"] {
    background: var(--color-surface-variant);
    color: var(--color-text-primary);
    border: 1px solid var(--color-border);
}

.stButton > button[kind="secondary"]:hover {
    background: var(--color-border);
}

/* Inputs */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > select {
    border-radius: var(--border-radius);
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    color: var(--color-text-primary);
    padding: 0.5rem 0.75rem;
    transition: var(--transition);
}

.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px rgba(var(--color-primary), 0.2);
}

/* Metrics */
[data-testid="metric-container"] {
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--border-radius);
    padding: calc(var(--spacing-unit) * 1.5);
    box-shadow: var(--shadow-sm);
}

[data-testid="metric-container"] label {
    color: var(--color-text-secondary) !important;
    font-weight: 500;
}

[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: var(--color-text-primary) !important;
    font-weight: 600;
}

/* Tables */
.stDataFrame {
    border: 1px solid var(--color-border);
    border-radius: var(--border-radius);
    overflow: hidden;
}

.stDataFrame thead th {
    background: var(--color-surface-variant);
    color: var(--color-text-primary);
    font-weight: 600;
    border-bottom: 2px solid var(--color-border);
}

.stDataFrame tbody tr:hover {
    background: var(--color-surface-variant);
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.5rem;
    background: transparent;
    border-bottom: 1px solid var(--color-divider);
    padding-bottom: 0;
}

.stTabs [data-baseweb="tab"] {
    border-radius: var(--border-radius) var(--border-radius) 0 0;
    padding: 0.75rem 1.5rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    transition: var(--transition);
}

.stTabs [data-baseweb="tab"]:hover {
    color: var(--color-text-primary);
    background: var(--color-surface-variant);
}

.stTabs [aria-selected="true"] {
    color: var(--color-primary) !important;
    border-bottom-color: var(--color-primary) !important;
}

/* Expanders */
.streamlit-expanderHeader {
    background: var(--color-surface);
    border: 1px solid var(--color-border) !important;
    border-radius: var(--border-radius) !important;
    color: var(--color-text-primary) !important;
    font-weight: 500;
}

.streamlit-expanderContent {
    border: 1px solid var(--color-border) !important;
    border-top: none !important;
    border-radius: 0 0 var(--border-radius) var(--border-radius) !important;
    background: var(--color-surface);
}

/* Sidebar */
.css-1d391kg {
    background: var(--color-surface);
    border-right: 1px solid var(--color-border);
}

/* Alerts/Notifications */
.stAlert {
    border-radius: var(--border-radius);
    border: none;
    box-shadow: var(--shadow-sm);
}

.stAlert > div {
    padding: 1rem 1.25rem;
}

/* Progress bars */
.stProgress > div > div > div {
    border-radius: var(--border-radius-sm);
    background: var(--color-primary);
}

/* Selectbox */
.stSelectbox > div > div {
    background: var(--color-surface);
}

/* Slider */
.stSlider > div > div > div > div {
    background: var(--color-primary);
}

/* Checkbox */
.stCheckbox > label > div:first-child {
    border-radius: var(--border-radius-sm);
    border: 2px solid var(--color-border);
}

.stCheckbox > label > div:first-child[data-checked="true"] {
    background: var(--color-primary);
    border-color: var(--color-primary);
}

/* Radio */
.stRadio > label > div:first-child {
    border-radius: var(--border-radius-sm);
}

/* File uploader */
.stFileUploader > div {
    border: 2px dashed var(--color-border);
    border-radius: var(--border-radius);
    background: var(--color-surface-variant);
    transition: var(--transition);
}

.stFileUploader > div:hover {
    border-color: var(--color-primary);
    background: rgba(var(--color-primary), 0.05);
}

/* Tooltip */
.stTooltipHoverTarget:hover + .stTooltip {
    background: var(--color-text-primary);
    color: var(--color-background);
    border-radius: var(--border-radius-sm);
    box-shadow: var(--shadow-lg);
}

/* Scrollbar */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

::-webkit-scrollbar-track {
    background: var(--color-surface-variant);
}

::-webkit-scrollbar-thumb {
    background: var(--color-border);
    border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--color-text-disabled);
}

/* Animations */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(-10px); }
    to { opacity: 1; transform: translateY(0); }
}

@keyframes slideIn {
    from { opacity: 0; transform: translateX(-20px); }
    to { opacity: 1; transform: translateX(0); }
}

.pro-animate-fade {
    animation: fadeIn 0.3s ease forwards;
}

.pro-animate-slide {
    animation: slideIn 0.3s ease forwards;
}

/* Focus visible */
*:focus-visible {
    outline: 2px solid var(--color-primary);
    outline-offset: 2px;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
}
</style>
"""


def inject_professional_css(config: ThemeConfig | None = None) -> str:
    """Inject professional CSS (including theme variables) into the app."""
    theme = config if isinstance(config, ThemeConfig) else ThemeConfig()
    css = theme.to_css_variables() + PROFESSIONAL_CSS
    st.markdown(css, unsafe_allow_html=True)
    return css


# Custom component helpers
def pro_card(title: str, content: str, icon: str = "", 
             action_label: str = "", action_key: str = "",
             expanded: bool = False) -> None:
    """Render a professional card component."""
    with st.container():
        st.markdown(f"""
        <div class="pro-card pro-animate-fade">
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
                {f'<span style="font-size: 1.5rem;">{icon}</span>' if icon else ''}
                <h4 style="margin: 0; color: var(--color-text-primary);">{title}</h4>
            </div>
            <div style="color: var(--color-text-secondary);">{content}</div>
        </div>
        """, unsafe_allow_html=True)
        
        if action_label:
            st.button(action_label, key=action_key, use_container_width=True)


def pro_metric_card(label: str, value: str, delta: str = "", 
                    delta_color: str = "normal", icon: str = "") -> None:
    """Render a professional metric card."""
    display_label = f"{icon} {label}".strip() if icon else label
    st.metric(
        display_label,
        value,
        delta=delta or None,
        delta_color=delta_color,
    )


def pro_status_badge(text: str, status: str = "info") -> None:
    """Render a professional status badge."""
    colors = {
        "success": ("var(--color-success)", "rgba(76, 175, 80, 0.1)"),
        "warning": ("var(--color-warning)", "rgba(255, 152, 0, 0.1)"),
        "error": ("var(--color-error)", "rgba(244, 67, 54, 0.1)"),
        "info": ("var(--color-info)", "rgba(33, 150, 243, 0.1)"),
        "neutral": ("var(--color-text-secondary)", "var(--color-surface-variant)"),
    }
    
    text_color, bg_color = colors.get(status, colors["info"])
    
    st.markdown(f"""
    <span style="
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        color: {text_color};
        background: {bg_color};
    ">{text}</span>
    """, unsafe_allow_html=True)


def pro_section_header(title: str, subtitle: str = "", action: str = "", 
                       action_key: str = "") -> bool:
    """Render a professional section header with optional action."""
    clicked = False

    st.subheader(title)
    if subtitle:
        st.caption(subtitle)

    if action:
        clicked = st.button(action, key=action_key, use_container_width=True)

    st.markdown("<hr style='border: none; border-top: 1px solid var(--color-divider); margin: 1rem 0;'>", unsafe_allow_html=True)

    return clicked


def pro_empty_state(title: str, description: str = "", icon: str = "",
                    action_label: str = "", action_key: str = "") -> bool:
    """Render a professional empty state."""
    clicked = False

    with st.container():
        st.markdown(f"""
        <div style="
            text-align: center;
            padding: 3rem 2rem;
            background: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: var(--border-radius);
        ">
            <div style="font-size: 3rem; margin-bottom: 1rem;">{icon}</div>
            <h3 style="margin: 0 0 0.5rem; color: var(--color-text-primary);">{title}</h3>
            <p style="margin: 0; color: var(--color-text-secondary);">{description}</p>
        </div>
        """, unsafe_allow_html=True)

        if action_label:
            clicked = st.button(action_label, key=action_key, type="primary", use_container_width=True)

    return clicked


def pro_data_table(data: list[dict] | "pd.DataFrame", columns: list[str] = None,
                    key: str = "", selection: bool = False, selection_mode: str = None) -> list[int]:
    """Render a professional data table with selection."""
    # Handle selection_mode as alias for selection
    if selection_mode is not None:
        selection = True
    import pandas as pd
    
    # Handle DataFrame input
    if isinstance(data, pd.DataFrame):
        if data.empty:
            pro_empty_state("📋", "No Data", "No records to display")
            return []
        data = data.to_dict('records')
    elif not data:
        pro_empty_state("📋", "No Data", "No records to display")
        return []
    
    df = pd.DataFrame(data)
    if columns:
        df = df[columns]
    
    # Add selection column if needed
    if selection:
        df.insert(0, "Select", False)
    
    # Use st.data_editor for selection
    editor_key = key if key else None
    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        key=editor_key,
        column_config={
            "Select": st.column_config.CheckboxColumn("Select", width="small"),
        } if selection else {},
        disabled=[c for c in df.columns if c != "Select"],
    )
    
    if selection:
        selected_indices = edited[edited["Select"]].index.tolist()
        return selected_indices
    
    return []


# Page layout helpers
def pro_page_header(title: str, subtitle: str = "", 
                    actions: list[tuple[str, str]] = None, icon: str = "") -> None:
    """Render professional page header."""
    if icon:
        title = f"{icon} {title}"
    # Call st.title for test compatibility
    st.title(title)
    if subtitle:
        st.caption(subtitle)
    st.markdown(f"""
    <div style="margin-bottom: 2rem;">
        <h1 style="margin: 0; color: var(--color-text-primary);">{title}</h1>
        {f'<p style="margin: 0.5rem 0 0; color: var(--color-text-secondary); font-size: 1.125rem;">{subtitle}</p>' if subtitle else ''}
    </div>
    """, unsafe_allow_html=True)
    
    if actions:
        cols = st.columns(len(actions))
        for i, (label, key) in enumerate(actions):
            with cols[i]:
                st.button(label, key=key, use_container_width=True)


def pro_two_column_layout(left_content: callable, right_content: callable,
                          left_width: int = 2, right_width: int = 1) -> None:
    """Render two-column layout with professional spacing."""
    col1, col2 = st.columns([left_width, right_width])
    with col1:
        left_content()
    with col2:
        right_content()


# Accessibility helpers
def announce_to_screen_reader(message: str) -> None:
    """Announce message to screen readers."""
    st.markdown(f"""
    <div aria-live="polite" aria-atomic="true" class="sr-only" style="position: absolute; left: -9999px;">
        {message}
    </div>
    """, unsafe_allow_html=True)


# Import demo function from ui module
from .ui import render_professional_ui_demo as _render_professional_ui_demo

# Expose demo function for backward compatibility
def render_professional_ui_demo():
    """Render the professional UI demo page (backward compatibility)."""
    return _render_professional_ui_demo()


# Responsive utilities
def is_mobile() -> bool:
    """Check if viewport is mobile (approximate)."""
    # This is a placeholder - in real app would use JS
    return False


def responsive_columns(breakpoints: dict[str, int]) -> list:
    """Create responsive columns based on breakpoints."""
    # Simplified - would need JS for true responsiveness
    return st.columns(breakpoints.get("desktop", 3))