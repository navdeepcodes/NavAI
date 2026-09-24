"""Turn Mike's Markdown into rich text the panel can show.

Mike answers in Markdown -- headings, lists, **bold**, fenced code, tables.
Rendered as escaped plain text (what the panel did before) that reads as a wall
of asterisks and backticks, which is exactly the "basic AI wrapper" feel a
coding/studying assistant cannot have. This renders it properly, staying inside
Qt's own rich-text engine (a QTextBrowser) rather than a web view, so it fits
the existing panel instead of replacing it.

Two things it does that a plain Markdown-to-HTML pass does not:

  - Code fences are syntax-highlighted with Pygments, themed to match Mike
    (a dark scheme in dark mode, a light one in light), on a sunk surface that
    reads as a code block rather than body text.
  - Each code block carries a copy affordance -- a `copy://N` link the widget
    intercepts -- so a student can lift a snippet in one click, which is the
    single most-used action on a coding answer.

Math (LaTeX) can't be typeset by Qt's rich text and there's no offline KaTeX,
so math spans are converted to real Unicode mathematics (see mathtext.py) and
set in Cambria Math — legible fractions, powers, roots, integrals and Greek,
instead of raw backslash commands.
"""
from __future__ import annotations

from html import escape

from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

from ui.panel import style

# CommonMark plus the things Mike actually uses: tables, and autolinked URLs.
_MD = (
    MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
    .enable("table")
    .enable("strikethrough")
)

# Pygments styles chosen to sit on Mike's own surfaces rather than clash: a
# muted light scheme on paper, a warm dark one on charcoal.
_LIGHT_PYGMENTS = "friendly"
_DARK_PYGMENTS = "one-dark"


def _pygments_style() -> str:
    return _DARK_PYGMENTS if style.is_dark() else _LIGHT_PYGMENTS


def _lexer(lang: str, code: str):
    lang = (lang or "").strip().lower()
    if lang:
        try:
            return get_lexer_by_name(lang)
        except ClassNotFound:
            pass
    try:
        return guess_lexer(code)
    except ClassNotFound:
        return get_lexer_by_name("text")


class _Renderer:
    """Collects code blocks while rendering so each gets a copy link."""

    def __init__(self, do_highlight: bool = True) -> None:
        self.codes: list[str] = []
        self._highlight = do_highlight

    def fence(self, tokens, idx, _options, _env) -> str:
        token = tokens[idx]
        code = token.content
        lang = (token.info or "").strip().split(" ")[0] if token.info else ""
        index = len(self.codes)
        self.codes.append(code.rstrip("\n"))

        # Highlighting is the expensive step, so it is skipped while a reply is
        # still streaming (the block re-renders on every token) and done once at
        # the end. During the stream the code is plain monospace; when Mike
        # finishes it resolves into full colour.
        if self._highlight:
            try:
                formatter = HtmlFormatter(noclasses=True, nowrap=True,
                                          style=_pygments_style())
                body = highlight(code, _lexer(lang, code), formatter)
            except Exception:
                body = escape(code)
        else:
            body = escape(code)

        sunk = style.GROUND_SUNK
        hair = style.HAIRLINE
        mute = style.INK_MUTE
        accent = style.accent()
        label = escape(lang) if lang else "code"
        # A header strip (language + a copy link) over the highlighted body.
        # Kept to inline styles and simple tags because Qt's rich text ignores
        # most of a real stylesheet.
        return (
            f'<table width="100%" cellspacing="0" cellpadding="0" '
            f'style="margin:8px 0; background:{sunk}; border:1px solid {hair};">'
            f'<tr><td style="padding:6px 12px; border-bottom:1px solid {hair};">'
            f'<span style="color:{mute}; font-size:11px;">{label}</span>'
            f'&nbsp;&nbsp;<a href="copy://{index}" '
            f'style="color:{accent}; font-size:11px; text-decoration:none;">'
            f'⧉ copy</a></td></tr>'
            f'<tr><td style="padding:10px 12px;">'
            f'<pre style="margin:0; font-family:Consolas,\'Cascadia Mono\',monospace; '
            f'font-size:12.5px; white-space:pre-wrap;">{body}</pre>'
            f'</td></tr></table>'
        )


def render(markdown_text: str, do_highlight: bool = True) -> tuple[str, list[str]]:
    """Render Markdown to Qt rich-text HTML.

    Returns (html, code_blocks) -- the code list is what the copy links refer to
    by index, so the widget can put block N on the clipboard. do_highlight is
    False while streaming, to skip the per-token syntax-highlighting cost.
    """
    if not markdown_text:
        return "", []
    renderer = _Renderer(do_highlight)
    _MD.renderer.rules["fence"] = renderer.fence
    _MD.renderer.rules["code_block"] = renderer.fence
    from ui.panel import mathtext

    # Math is lifted out first (Markdown would read x_1 or a*b as emphasis)
    # and put back, converted, after rendering.
    try:
        prepared, maths = mathtext.extract(markdown_text)
    except Exception:
        prepared, maths = markdown_text, []
    try:
        body = _MD.render(prepared)
        body = mathtext.restore(body, maths)
    except Exception:
        body = f"<p>{escape(markdown_text)}</p>"

    # A thin wrapper carries the body text colour and reading measure; inline
    # code gets a faint tint so it reads as code without a full block.
    ink = style.INK
    tint = style.GROUND_RAISED
    wrapped = (
        f'<div style="color:{ink}; font-family:{style.ui_family()}; '
        f'font-size:16px; line-height:150%;">{body}</div>'
    )
    # Qt renders <code> plainly; give inline code a tinted background via a
    # post-process, since markdown-it emits bare <code>.
    wrapped = wrapped.replace(
        "<code>",
        f'<code style="background:{tint}; font-family:Consolas,monospace; '
        f'font-size:13px;">')
    return wrapped, renderer.codes
