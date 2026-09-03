from __future__ import annotations

import re

from ui.theme import colors
from ui.theme import typography


def md_to_html(text: str) -> str:
    """Convert basic markdown to HTML for QLabel rich text."""

    lines = text.split("\n")
    out = []
    in_code_block = False

    for line in lines:

        # Fenced code blocks
        if line.strip().startswith("```"):
            if in_code_block:
                out.append("</pre>")
                in_code_block = False
            else:
                out.append(
                    f'<pre style="background: {colors.SURFACE_ELEVATED};'
                    f" padding: 10px 14px; border-radius: 8px;"
                    f' font-family: {typography.MONO_FONT}; font-size: 13px;'
                    f' color: {colors.TEXT};">'
                )
                in_code_block = True
            continue

        if in_code_block:
            out.append(_escape(line))
            continue

        # Blank line → paragraph break
        if not line.strip():
            out.append("<br/>")
            continue

        # Bullet lists
        m = re.match(r"^(\s*)[-*]\s+(.+)$", line)
        if m:
            indent = len(m.group(1)) // 2
            content = _inline(m.group(2))
            pad = 8 + indent * 16
            out.append(
                f'<div style="padding-left: {pad}px; margin: 3px 0;">'
                f'<span style="color: {colors.TEXT_MUTED};">•</span>'
                f"  {content}</div>"
            )
            continue

        # Numbered lists
        m = re.match(r"^(\s*)(\d+)[.)]\s+(.+)$", line)
        if m:
            indent = len(m.group(1)) // 2
            num = m.group(2)
            content = _inline(m.group(3))
            pad = 8 + indent * 16
            out.append(
                f'<div style="padding-left: {pad}px; margin: 3px 0;">'
                f'<span style="color: {colors.TEXT_MUTED};">{num}.</span>'
                f"  {content}</div>"
            )
            continue

        # Regular paragraph
        out.append(f"<div>{_inline(line)}</div>")

    if in_code_block:
        out.append("</pre>")

    return "".join(out)


def _inline(text: str) -> str:
    """Apply inline markdown formatting."""

    # Bold: **text** or __text__
    text = re.sub(
        r"\*\*(.+?)\*\*",
        r"<b>\1</b>",
        text,
    )
    text = re.sub(
        r"__(.+?)__",
        r"<b>\1</b>",
        text,
    )

    # Italic: *text* or _text_ (but not inside words with underscores)
    text = re.sub(
        r"(?<!\w)\*([^*]+?)\*(?!\w)",
        r"<i>\1</i>",
        text,
    )

    # Inline code: `text`
    text = re.sub(
        r"`([^`]+?)`",
        lambda m: (
            f'<code style="background: {colors.SURFACE_ELEVATED};'
            f" padding: 2px 6px; border-radius: 4px;"
            f' font-family: {typography.MONO_FONT}; font-size: 13px;">'
            f"{_escape(m.group(1))}</code>"
        ),
        text,
    )

    return text


def _escape(text: str) -> str:
    """Escape HTML entities."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
