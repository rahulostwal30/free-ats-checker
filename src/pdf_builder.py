"""Render Markdown (resume or analysis report) into a formatted PDF.

Layout comes from a ResumeTheme (see src/resume_themes.py). The Markdown is
parsed directly, so headings, bullets, bold text and long lines keep their
structure and wrap correctly. Output is always single-column text.
"""

import io
import re
from typing import List, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from src.resume_themes import DEFAULT_THEME, ResumeTheme, get_theme

_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC = re.compile(
    r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])|(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])"
)
_HORIZONTAL_RULE = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^[-*\u2022]\s+(.*)$")


def _clean_text(text: str) -> str:
    """Make text safe for ReportLab's built-in fonts (WinAnsi encoding)."""
    text = _EMOJI.sub("", text)
    text = text.replace("\u2192", "->").replace("\u00a0", " ").replace("\u200b", "")
    return text.encode("cp1252", errors="replace").decode("cp1252")


def _to_markup(text: str) -> str:
    """Convert a Markdown inline snippet into ReportLab paragraph markup."""
    text = escape(_clean_text(text))
    text = _LINK.sub(
        lambda m: m.group(2) if m.group(1) == m.group(2) else f"{m.group(1)} ({m.group(2)})",
        text,
    )
    text = _CODE.sub(lambda m: m.group(1), text)
    text = _BOLD.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text)
    text = _ITALIC.sub(lambda m: f"<i>{m.group(1) or m.group(2)}</i>", text)
    return text


def build_styles(theme: ResumeTheme) -> dict:
    align = TA_CENTER if theme.name_align == "center" else TA_LEFT
    ink = colors.HexColor(theme.text)
    muted = colors.HexColor(theme.muted)
    contact_size = theme.body_size - 0.5
    return {
        "title": ParagraphStyle(
            "title", fontName=theme.font_bold, fontSize=theme.name_size,
            leading=theme.name_size * 1.2, textColor=ink, alignment=align, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", fontName=theme.subtitle_font, fontSize=theme.subtitle_size,
            leading=theme.subtitle_size * 1.3, textColor=colors.HexColor(theme.subtitle_color),
            alignment=align, spaceAfter=4,
        ),
        "contact": ParagraphStyle(
            "contact", fontName=theme.font, fontSize=contact_size,
            leading=contact_size * 1.3, textColor=muted, alignment=align, spaceAfter=6,
        ),
        "section": ParagraphStyle(
            "section", fontName=theme.font_bold, fontSize=theme.section_size,
            leading=theme.section_size * 1.25, textColor=colors.HexColor(theme.section_color),
            spaceBefore=theme.section_before, spaceAfter=2,
        ),
        "entry": ParagraphStyle(
            "entry", fontName=theme.font_bold, fontSize=theme.entry_size,
            leading=theme.entry_size * 1.3, textColor=ink,
            spaceBefore=theme.entry_before, spaceAfter=1,
        ),
        "body": ParagraphStyle(
            "body", fontName=theme.font, fontSize=theme.body_size,
            leading=theme.body_leading, textColor=ink, spaceAfter=3,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName=theme.font, fontSize=theme.body_size,
            leading=theme.body_leading, textColor=ink,
            leftIndent=12, bulletIndent=2, spaceAfter=theme.bullet_after,
        ),
        "note": ParagraphStyle(
            "note", fontName=theme.font, fontSize=9, leading=12, textColor=muted, spaceAfter=8,
        ),
    }


def _paragraph(text: str, style: ParagraphStyle, bullet: Optional[str] = None) -> Paragraph:
    try:
        return Paragraph(_to_markup(text), style, bulletText=bullet)
    except Exception:
        # Fall back to plain escaped text if the markup is unusual.
        return Paragraph(escape(_clean_text(text)), style, bulletText=bullet)


def _section_rule(theme: ResumeTheme):
    if theme.rule_color:
        return HRFlowable(
            width="100%",
            thickness=theme.rule_thickness,
            color=colors.HexColor(theme.rule_color),
            spaceBefore=0,
            spaceAfter=4,
        )
    return Spacer(1, 2)


def markdown_to_flowables(markdown_text: str, theme: Optional[ResumeTheme] = None) -> List:
    theme = theme or get_theme(DEFAULT_THEME)
    styles = build_styles(theme)
    story: List = []
    paragraph_lines: List[str] = []
    in_section = False

    def flush_paragraph() -> None:
        if paragraph_lines:
            style = styles["body"] if in_section else styles["contact"]
            story.append(_paragraph(" ".join(paragraph_lines), style))
            paragraph_lines.clear()

    for raw_line in (markdown_text or "").splitlines():
        line = raw_line.strip()

        if not line:
            flush_paragraph()
            continue

        if _HORIZONTAL_RULE.match(line):
            # Section headings already draw a rule, so separators are skipped.
            flush_paragraph()
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            text = heading.group(2).strip().rstrip("#").strip()
            if level == 1:
                story.append(_paragraph(text.upper() if theme.name_uppercase else text, styles["title"]))
            elif level == 2:
                in_section = True
                story.append(_paragraph(text.upper() if theme.section_uppercase else text, styles["section"]))
                story.append(_section_rule(theme))
            else:
                story.append(_paragraph(text, styles["entry"] if in_section else styles["subtitle"]))
            continue

        bullet = _BULLET.match(line)
        if bullet:
            flush_paragraph()
            story.append(_paragraph(bullet.group(1), styles["bullet"], bullet="\u2022"))
            continue

        paragraph_lines.append(line)

    flush_paragraph()
    return story


def markdown_to_pdf_bytes(
    markdown_text: str,
    document_title: str = "Document",
    header_title: Optional[str] = None,
    header_note: Optional[str] = None,
    theme_key: str = DEFAULT_THEME,
) -> bytes:
    """Build an A4 PDF from Markdown text using the chosen theme."""
    theme = get_theme(theme_key)
    styles = build_styles(theme)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=theme.margin_x_mm * mm,
        rightMargin=theme.margin_x_mm * mm,
        topMargin=theme.margin_y_mm * mm,
        bottomMargin=theme.margin_y_mm * mm,
        title=document_title,
        author="Free AI ATS Resume Checker",
    )

    story: List = []
    if header_title:
        story.append(_paragraph(header_title, styles["title"]))
    if header_note:
        story.append(_paragraph(header_note, styles["note"]))

    story.extend(markdown_to_flowables(markdown_text, theme))
    if not story:
        story.append(_paragraph("No content available.", styles["body"]))

    doc.build(story)
    return buffer.getvalue()
