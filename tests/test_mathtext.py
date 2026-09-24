"""Maths in Mike's answers must read as maths, not LaTeX source.

Local models write heavier maths as LaTeX, and Qt's rich text can't typeset it,
so a student saw "\\frac{x^3}{3} + C". Math spans are converted to Unicode
mathematics — while money, code and ordinary prose are left exactly alone.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui.panel.mathtext import extract, latex_to_unicode as L


def test_common_student_maths():
    assert L(r"\frac{x^3}{3} + C") == "x³/3 + C"
    assert L(r"\int_0^3 x^2\,dx") == "∫₀³ x² dx"
    assert L(r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}") == "x = (−b ± √(b² − 4ac))/2a"
    assert L(r"\sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6}") == "∑ₙ₌₁^∞ 1/n² = π²/6"
    assert L(r"\sqrt[3]{27} = 3") == "∛27 = 3"
    assert L(r"90^\circ") == "90°"
    assert L(r"H_2O") == "H₂O"
    assert L(r"\alpha + \beta \geq \gamma") == "α + β ≥ γ"
    assert L(r"\text{Area} = \pi r^2") == "Area = π r²"


def test_limits_read_naturally():
    out = L(r"\lim_{x \to 0} \frac{\sin x}{x} = 1")
    assert out.startswith("lim(x → 0)")
    assert "\\" not in out


def test_money_code_and_prose_are_untouched():
    md = ("It costs $5 and $10.\n\n"
          "```python\nx = a_b * 2  # $not^math$\n```\n\n"
          "Use `pip install x_y` then relax.")
    out, found = extract(md)
    assert "$5 and $10" in out
    assert "x = a_b * 2  # $not^math$" in out
    assert "`pip install x_y`" in out
    assert found == []


def test_plain_variables_and_simple_algebra_are_maths_but_prices_are_not():
    """Models write "$Q$ — heat added" constantly; it showed as raw "$Q$"."""
    out, found = extract("- $Q$ — heat added\n- $W$ — work done, where $x = 3$")
    assert "$" not in out
    assert [t for _d, t in found] == ["Q", "W", "x = 3"]
    for prose in ("It costs $5 and $10.", "between $5-$6", "I paid $20 and $ was gone"):
        _out, found = extract(prose)
        assert found == [], prose


def test_all_delimiters_are_found():
    md = (r"Area is $\pi r^2$, inline \(e^{i\pi}\)." "\n\n"
          r"$$\int_0^1 x\,dx = \frac{1}{2}$$" "\n\n"
          r"\[a^2 + b^2 = c^2\]")
    out, found = extract(md)
    texts = [t for _d, t in found]
    assert "π r²" in texts
    assert "∫₀¹ x dx = 1/2" in texts
    assert "a² + b² = c²" in texts
    display = {t for d, t in found if d}
    assert display == {"∫₀¹ x dx = 1/2", "a² + b² = c²"}
    assert "\\" not in "".join(texts)


def test_rendered_html_contains_no_raw_latex():
    from ui.panel.richtext import render
    html, _codes = render(r"The antiderivative is $\frac{x^3}{3} + C$.")
    assert "\\frac" not in html
    assert "x³/3 + C" in html
    assert "Cambria Math" in html
