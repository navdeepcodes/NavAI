"""Make LaTeX math readable in Mike's answers.

Local models write heavier maths as LaTeX — ``\\frac{x^3}{3} + C``,
``\\int_0^3 x^2\\,dx``, ``\\sqrt{b^2 - 4ac}`` — and Qt's rich text can't typeset
it, so a student saw backslash soup. There is no offline KaTeX in this build,
so math spans are rewritten into real Unicode mathematics (x³/3, ∫₀³ x² dx,
√(b² − 4ac)) and set in Cambria Math, which ships with every Windows install.
That covers what a student actually meets — fractions, powers, roots,
integrals, sums, limits, Greek letters, relations — legibly, with no web view.

Only text inside math delimiters is touched: ``$$…$$``, ``\\[…\\]``, ``\\(…\\)``
and ``$…$`` (the last only when it plainly holds maths, so "$5 and $10" stays
money). Fenced and inline code are never touched.
"""
from __future__ import annotations

import re
from html import escape

_SUP = dict(zip("0123456789+-=()nia bcdefghjklmoprstuvwxyzT",
                "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱᵃ ᵇᶜᵈᵉᶠᵍʰʲᵏˡᵐᵒᵖʳˢᵗᵘᵛʷˣʸᶻᵀ"))
_SUB = dict(zip("0123456789+-=()aehijklmnoprstuvx ",
                "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ "))

_SYMBOLS = {
    "pm": "±", "mp": "∓", "times": "×", "div": "÷", "cdot": "·", "ast": "∗",
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "neq": "≠", "ne": "≠",
    "approx": "≈", "equiv": "≡", "sim": "∼", "simeq": "≃", "propto": "∝",
    "infty": "∞", "int": "∫", "iint": "∬", "iiint": "∭", "oint": "∮",
    "sum": "∑", "prod": "∏", "partial": "∂", "nabla": "∇",
    "to": "→", "rightarrow": "→", "Rightarrow": "⇒", "leftarrow": "←",
    "Leftarrow": "⇐", "leftrightarrow": "↔", "Leftrightarrow": "⇔",
    "implies": "⇒", "iff": "⇔", "mapsto": "↦",
    "in": "∈", "notin": "∉", "subset": "⊂", "subseteq": "⊆", "supset": "⊃",
    "cup": "∪", "cap": "∩", "emptyset": "∅", "varnothing": "∅",
    "forall": "∀", "exists": "∃", "neg": "¬", "land": "∧", "lor": "∨",
    "angle": "∠", "degree": "°", "circ": "∘", "perp": "⊥", "parallel": "∥",
    "cdots": "⋯", "ldots": "…", "dots": "…", "therefore": "∴", "because": "∵",
    "mid": "|", "vert": "|", "lVert": "‖", "rVert": "‖", "|": "‖",
    "langle": "⟨", "rangle": "⟩", "lfloor": "⌊", "rfloor": "⌋",
    "lceil": "⌈", "rceil": "⌉", "prime": "′", "hbar": "ℏ", "ell": "ℓ",
    "Re": "ℜ", "Im": "ℑ", "aleph": "ℵ",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ϵ",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ",
    "phi": "ϕ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "{": "{", "}": "}", "%": "%", "$": "$", "&": "&", "#": "#", "_": "_",
}
#: Spoken-as-words operators: keep the word, drop the backslash.
_WORDS = {"sin", "cos", "tan", "sec", "csc", "cot", "arcsin", "arccos",
          "arctan", "sinh", "cosh", "tanh", "log", "ln", "exp", "lim", "max",
          "min", "sup", "inf", "det", "gcd", "deg", "dim", "ker", "arg", "mod"}
#: Commands whose braced argument is just shown as-is.
_PASS = {"text", "mathrm", "mathbf", "mathit", "mathsf", "mathtt", "boldsymbol",
         "operatorname", "textbf", "textit", "mbox", "displaystyle", "mathbb",
         "mathcal", "bm", "vec", "hat", "bar", "overline", "tilde", "dot"}
_SPACES = {",", ";", ":", "!", " ", "quad", "qquad", "enspace", "thinspace"}
_DROP = {"left", "right", "big", "Big", "bigg", "Bigg", "limits", "nolimits"}


def _read_group(s: str, i: int) -> tuple[str, int]:
    """Return the next argument at s[i] — a {braced} group or one token."""
    while i < len(s) and s[i] == " ":
        i += 1
    if i >= len(s):
        return "", i
    if s[i] == "{":
        depth, j = 1, i + 1
        while j < len(s) and depth:
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
            j += 1
        return s[i + 1:j - 1], j
    if s[i] == "\\":
        m = re.match(r"\\([A-Za-z]+|.)", s[i:])
        return m.group(0), i + len(m.group(0))
    return s[i], i + 1


def _script(text: str, table: dict, mark: str) -> str:
    if text and all(c in table for c in text):
        return "".join(table[c] for c in text)
    return f"{mark}({text})" if len(text) > 1 else f"{mark}{text}"


_SCRIPTS = "".join(set(_SUP.values()) | set(_SUB.values())).replace(" ", "")


def _simple(text: str) -> bool:
    """A single term that needs no brackets around it in a fraction."""
    return bool(re.fullmatch(r"[A-Za-z0-9α-ωΑ-Ωϵϑϕ.′" + re.escape(_SCRIPTS) + r"]+", text))


def latex_to_unicode(src: str) -> str:
    """Convert one LaTeX math expression to readable Unicode."""
    s = src.replace("\\\\", " ; ").replace("&", " ")
    s = re.sub(r"\\(begin|end)\{[^}]*\}", " ", s)
    out: list[str] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", s[i:])
            name = m.group(1)
            i += len(m.group(0))
            if name in _SPACES:
                out.append(" ")
            elif name in _DROP:
                pass
            elif name == "frac" or name in ("dfrac", "tfrac"):
                num, i = _read_group(s, i)
                den, i = _read_group(s, i)
                num, den = latex_to_unicode(num), latex_to_unicode(den)
                num = num if _simple(num) else f"({num})"
                den = den if _simple(den) else f"({den})"
                out.append(f"{num}/{den}")
            elif name == "sqrt":
                root = ""
                if i < len(s) and s[i] == "[":
                    j = s.index("]", i)
                    root, i = s[i + 1:j], j + 1
                arg, i = _read_group(s, i)
                arg = latex_to_unicode(arg)
                sign = {"3": "∛", "4": "∜"}.get(root, "√")
                if root and root not in ("3", "4"):
                    sign = _script(root, _SUP, "^") + "√"
                out.append(sign + (arg if _simple(arg) else f"({arg})"))
            elif name in _PASS:
                arg, i = _read_group(s, i)
                out.append(latex_to_unicode(arg))
            elif name in _SYMBOLS:
                out.append(_SYMBOLS[name])
            elif name in _WORDS:
                out.append(name)
            else:
                out.append(name)
        elif c in "^_":
            arg, i = _read_group(s, i + 1)
            arg = latex_to_unicode(arg)
            compact = arg.replace(" ", "").replace("−", "-")
            table = _SUP if c == "^" else _SUB
            prev = "".join(out).rstrip()
            if c == "^" and compact in ("∘", "°"):
                out.append("°")
            elif c == "^" and compact == "′":
                out.append("′")
            elif compact and all(ch in table for ch in compact):
                out.append("".join(table[ch] for ch in compact))
            elif c == "_" and re.search(r"(lim|max|min|sup|inf)$", prev):
                # lim_{x→0} reads naturally as "lim(x → 0)"
                out.append(f"({arg}) ")
            else:
                out.append(_script(arg, table, c))
        elif c in "{}":
            i += 1
        else:
            out.append({"-": "−", "*": "·"}.get(c, c))
            i += 1
    text = "".join(out)
    text = re.sub(r"\s+", " ", text).strip(" ;")
    return re.sub(r"\s*([=<>≤≥≠≈±→⇒])\s*", r" \1 ", text).strip()


# ── finding math in Markdown ────────────────────────────────

_FENCE = re.compile(r"(```.*?(?:```|$)|~~~.*?(?:~~~|$))", re.DOTALL)
_INLINE_CODE = re.compile(r"(`+)(.+?)\1", re.DOTALL)
_DISPLAY = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]", re.DOTALL)
_INLINE = re.compile(r"\\\((.+?)\\\)", re.DOTALL)
# $…$ only when it's unmistakably maths: no space just inside the dollars, not
# followed by a digit (so "$5 and $10" is money), and holding a TeX command or
# a ^/_ script.
_DOLLAR = re.compile(r"(?<![\\$\w])\$(?=\S)([^$\n]*?[\\^_][^$\n]*?)(?<=\S)\$(?![\d$])")

PLACEHOLDER = "\u2063M{}\u2063"


def extract(markdown_text: str) -> tuple[str, list[tuple[bool, str]]]:
    """Swap math spans for placeholders (so Markdown can't mangle them) and
    return their Unicode renderings, as (is_display, text)."""
    found: list[tuple[bool, str]] = []

    def stash(display: bool, expr: str) -> str:
        found.append((display, latex_to_unicode(expr)))
        return PLACEHOLDER.format(len(found) - 1)

    def in_prose(chunk: str) -> str:
        code: list[str] = []

        def keep(m):
            code.append(m.group(0))
            return f"\u2063C{len(code) - 1}\u2063"

        chunk = _INLINE_CODE.sub(keep, chunk)
        chunk = _DISPLAY.sub(lambda m: stash(True, m.group(1) or m.group(2)), chunk)
        chunk = _INLINE.sub(lambda m: stash(False, m.group(1)), chunk)
        chunk = _DOLLAR.sub(lambda m: stash(False, m.group(1)), chunk)
        return re.sub("\u2063C(\\d+)\u2063", lambda m: code[int(m.group(1))], chunk)

    parts = _FENCE.split(markdown_text)
    rebuilt = [p if _FENCE.fullmatch(p) else in_prose(p) for p in parts]
    return "".join(rebuilt), found


def restore(html: str, found: list[tuple[bool, str]]) -> str:
    """Put the rendered math back into Markdown's HTML output."""
    def span(m):
        display, text = found[int(m.group(1))]
        size = "18px" if display else "16px"
        return (f'<span style="font-family:\'Cambria Math\',\'Segoe UI Symbol\','
                f'serif; font-size:{size};">{escape(text)}</span>')

    return re.sub("\u2063M(\\d+)\u2063", span, html)
