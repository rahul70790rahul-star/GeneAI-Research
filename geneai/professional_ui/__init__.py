"""GeneAI Professional User Interface - Phase 5.8."""
from __future__ import annotations

from geneai.professional_ui.core import (
    ThemeMode,
    ColorScheme,
    ThemeColors,
    DarkThemeColors,
    HighContrastThemeColors,
    ThemeConfig,
    THEMES,
    COLOR_SCHEMES,
    apply_theme,
    render_theme_selector,
    inject_professional_css,
    pro_card,
    pro_metric_card,
    pro_status_badge,
    pro_section_header,
    pro_empty_state,
    pro_data_table,
    pro_page_header,
    pro_two_column_layout,
    announce_to_screen_reader,
    adjust_color,
)
from geneai.professional_ui.ui import (
    render_professional_ui_demo,
    render as render_professional_ui,
)

__all__ = [
    # Core
    "ThemeMode",
    "ColorScheme",
    "ThemeColors",
    "DarkThemeColors",
    "HighContrastThemeColors",
    "ThemeConfig",
    "THEMES",
    "COLOR_SCHEMES",
    "apply_theme",
    "render_theme_selector",
    "inject_professional_css",
    "pro_card",
    "pro_metric_card",
    "pro_status_badge",
    "pro_section_header",
    "pro_empty_state",
    "pro_data_table",
    "pro_page_header",
    "pro_two_column_layout",
    "announce_to_screen_reader",
    "adjust_color",
    # UI
    "render_professional_ui_demo",
    "render_professional_ui",
]

__version__ = "5.8.0"