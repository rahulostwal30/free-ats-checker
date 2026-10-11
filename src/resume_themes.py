"""ATS-friendly resume templates.

Each template is a ResumeTheme. The same values drive the PDF (ReportLab) and
the on-screen preview (CSS), so the preview matches the downloaded file.

All templates are single-column and text-only: no tables, columns, icons,
images, text boxes, or header/footer text. Many ATS parsers skip or scramble
those, so they are not used.
"""

from dataclasses import asdict, dataclass
from typing import List, Optional

PX_PER_PT = 1.333  # CSS pixels per typographic point
PX_PER_MM = 3.78   # CSS pixels per millimetre


@dataclass(frozen=True)
class ResumeTheme:
    key: str
    name: str
    description: str
    font: str            # ReportLab built-in font for body text
    font_bold: str       # ReportLab built-in bold font
    css_font: str        # CSS font-family for the on-screen preview
    text: str            # main text colour (hex)
    muted: str           # contact line colour (hex)
    accent: str          # accent colour (hex)
    name_size: float     # pt
    name_align: str      # "left" or "center"
    name_uppercase: bool
    subtitle_font: str   # ReportLab font for the job-title line
    subtitle_size: float
    subtitle_color: str
    section_size: float
    section_color: str
    section_uppercase: bool
    rule_color: str      # hex, or "" for no rule under section headings
    rule_thickness: float
    body_size: float
    body_leading: float
    entry_size: float
    section_before: float
    entry_before: float
    bullet_after: float
    margin_x_mm: float
    margin_y_mm: float


THEMES = {
    "classic": ResumeTheme(
        key="classic",
        name="Classic",
        description="Times font, centred name, black and white. Suits corporate, finance and government roles.",
        font="Times-Roman",
        font_bold="Times-Bold",
        css_font='"Times New Roman", Times, serif',
        text="#111111",
        muted="#333333",
        accent="#000000",
        name_size=22,
        name_align="center",
        name_uppercase=False,
        subtitle_font="Times-Italic",
        subtitle_size=11.5,
        subtitle_color="#000000",
        section_size=11,
        section_color="#000000",
        section_uppercase=True,
        rule_color="#000000",
        rule_thickness=0.8,
        body_size=10.5,
        body_leading=13.5,
        entry_size=10.8,
        section_before=12,
        entry_before=6,
        bullet_after=2,
        margin_x_mm=20,
        margin_y_mm=18,
    ),
    "modern": ResumeTheme(
        key="modern",
        name="Modern",
        description="Helvetica font, left-aligned name, dark blue accents. Suits tech and startup roles.",
        font="Helvetica",
        font_bold="Helvetica-Bold",
        css_font="Helvetica, Arial, sans-serif",
        text="#111827",
        muted="#4B5563",
        accent="#1E3A8A",
        name_size=20,
        name_align="left",
        name_uppercase=False,
        subtitle_font="Helvetica-Bold",
        subtitle_size=11,
        subtitle_color="#1E3A8A",
        section_size=10.5,
        section_color="#111827",
        section_uppercase=True,
        rule_color="#1E3A8A",
        rule_thickness=0.8,
        body_size=9.5,
        body_leading=13,
        entry_size=10,
        section_before=10,
        entry_before=5,
        bullet_after=1.5,
        margin_x_mm=18,
        margin_y_mm=16,
    ),
    "minimal": ResumeTheme(
        key="minimal",
        name="Minimal",
        description="Generous white space, no colours, thin dividers. Looks clean everywhere.",
        font="Helvetica",
        font_bold="Helvetica-Bold",
        css_font="Helvetica, Arial, sans-serif",
        text="#111111",
        muted="#6B7280",
        accent="#111111",
        name_size=18,
        name_align="left",
        name_uppercase=False,
        subtitle_font="Helvetica",
        subtitle_size=10.5,
        subtitle_color="#374151",
        section_size=9.5,
        section_color="#111111",
        section_uppercase=True,
        rule_color="#D1D5DB",
        rule_thickness=0.6,
        body_size=9.5,
        body_leading=13.5,
        entry_size=9.8,
        section_before=14,
        entry_before=6,
        bullet_after=2,
        margin_x_mm=22,
        margin_y_mm=20,
    ),
    "compact": ResumeTheme(
        key="compact",
        name="Compact",
        description="Tighter spacing so a fresher's resume fits on one page.",
        font="Helvetica",
        font_bold="Helvetica-Bold",
        css_font="Helvetica, Arial, sans-serif",
        text="#111827",
        muted="#4B5563",
        accent="#1E3A8A",
        name_size=17,
        name_align="left",
        name_uppercase=False,
        subtitle_font="Helvetica-Bold",
        subtitle_size=10,
        subtitle_color="#1E3A8A",
        section_size=9.5,
        section_color="#1E3A8A",
        section_uppercase=True,
        rule_color="#1E3A8A",
        rule_thickness=0.6,
        body_size=8.8,
        body_leading=11.2,
        entry_size=9.2,
        section_before=7,
        entry_before=3,
        bullet_after=0.8,
        margin_x_mm=13,
        margin_y_mm=11,
    ),
}

THEME_ORDER: List[str] = ["classic", "modern", "minimal", "compact"]
DEFAULT_THEME = "modern"


def get_theme(key: Optional[str]) -> ResumeTheme:
    """Return the requested theme, or the default one for unknown keys."""
    return THEMES.get((key or "").strip().lower(), THEMES[DEFAULT_THEME])


def theme_choices() -> List[dict]:
    """Theme data for the template picker on the builder page."""
    return [asdict(THEMES[key]) for key in THEME_ORDER]


def _px(pt: float) -> float:
    return round(pt * PX_PER_PT, 1)


def _font_style(font_name: str) -> str:
    lowered = font_name.lower()
    weight = "700" if "bold" in lowered else "400"
    style = "italic" if ("italic" in lowered or "oblique" in lowered) else "normal"
    return f"font-weight: {weight}; font-style: {style};"


def theme_css(theme: ResumeTheme) -> str:
    """CSS for the on-screen preview. Mirrors the PDF layout of the theme."""
    align = theme.name_align
    name_case = "uppercase" if theme.name_uppercase else "none"
    section_case = "uppercase" if theme.section_uppercase else "none"
    if theme.rule_color:
        rule = f"border-bottom: {_px(theme.rule_thickness)}px solid {theme.rule_color};"
    else:
        rule = "border-bottom: none;"

    return f"""
.resume-paper {{
    font-family: {theme.css_font};
    font-size: {_px(theme.body_size)}px;
    line-height: {_px(theme.body_leading)}px;
    color: {theme.text};
    padding: {round(theme.margin_y_mm * PX_PER_MM)}px {round(theme.margin_x_mm * PX_PER_MM)}px;
}}
.resume-paper h1 {{
    font-family: {theme.css_font};
    font-weight: 700;
    font-size: {_px(theme.name_size)}px;
    line-height: 1.15;
    color: {theme.text};
    text-align: {align};
    text-transform: {name_case};
    margin: 0 0 2px;
}}
.resume-paper h1 + h3 {{
    font-family: {theme.css_font};
    {_font_style(theme.subtitle_font)}
    font-size: {_px(theme.subtitle_size)}px;
    line-height: 1.3;
    color: {theme.subtitle_color};
    text-align: {align};
    margin: 0 0 4px;
}}
.resume-paper h1 + h3 + p {{
    font-size: {_px(theme.body_size - 0.5)}px;
    color: {theme.muted};
    text-align: {align};
    margin: 0 0 8px;
}}
.resume-paper h2 {{
    font-family: {theme.css_font};
    font-weight: 700;
    font-style: normal;
    font-size: {_px(theme.section_size)}px;
    line-height: 1.3;
    color: {theme.section_color};
    text-transform: {section_case};
    margin: {_px(theme.section_before)}px 0 6px;
    padding-bottom: 3px;
    {rule}
}}
.resume-paper h3 {{
    font-family: {theme.css_font};
    font-weight: 700;
    font-style: normal;
    font-size: {_px(theme.entry_size)}px;
    line-height: 1.3;
    color: {theme.text};
    margin: {_px(theme.entry_before)}px 0 2px;
}}
.resume-paper p {{
    margin: 0 0 4px;
}}
.resume-paper ul {{
    margin: 0 0 4px;
    padding-left: 20px;
}}
.resume-paper li {{
    margin-bottom: {_px(theme.bullet_after)}px;
}}
.resume-paper hr {{
    display: none;
}}
"""
