"""Exact arithmetic, and the reason it exists.

On a six-workbook long-horizon run Mike read every file correctly, wrote
every cell correctly, and held the goal for fifteen turns — and totalled
2417 + 3168 + 912 as 6500 instead of 6497 on the first workbook, then carried
that figure into the summary so consistently that it looked deliberate.
Nothing in the runtime could catch it, because nothing in the runtime could
add.

The tool decides nothing and sequences nothing. It evaluates an expression.
The safety requirement is that a string coming from a model, or from a
document a model read, cannot reach anything but arithmetic.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import _isolate  # noqa: F401

import pytest

from tools.compute.calculator import calculate


# ── it computes ───────────────────────────────────────────

@pytest.mark.parametrize("expression,expected", [
    ("2417 + 3168 + 912", 6497),          # the figure from the real run
    ("1 + 2 * 3", 7),
    ("(1 + 2) * 3", 9),
    ("10 / 4", 2.5),
    ("10 // 4", 2),
    ("10 % 3", 1),
    ("2 ** 10", 1024),
    ("-5 + 3", -2),
    ("sum([2417, 3168, 912])", 6497),
    ("max(3, 9, 2)", 9),
    ("min([4, 1, 7])", 1),
    ("abs(-12)", 12),
    ("round(7 / 3, 2)", 2.33),
    ("sqrt(144)", 12),
    ("floor(2.9)", 2),
    ("ceil(2.1)", 3),
])
def test_arithmetic(expression, expected):
    result = calculate(expression)
    assert result["status"] == "success", result.get("error")
    assert result["value"] == expected


def test_a_whole_number_answer_is_not_returned_as_a_float():
    """9304.0 in a spreadsheet cell is not the same as 9304 to a person
    reading it, and it is the value that gets written."""
    result = calculate("10 / 2")
    assert result["value"] == 5
    assert isinstance(result["value"], int)


def test_thousands_separators_are_understood():
    assert calculate("1,234 + 1")["value"] == 1235
    assert calculate("1,234,567 + 0")["value"] == 1234567


def test_a_list_separator_is_not_mistaken_for_a_thousands_separator():
    """Stripping every comma turned sum([1,2,3]) into sum([123]) — a wrong
    answer delivered with total confidence, which is the one thing this tool
    must never do."""
    assert calculate("sum([1,2,3])")["value"] == 6


def test_percentages_are_understood():
    assert calculate("50% * 200")["value"] == 100
    assert calculate("15% * 80")["value"] == 12


def test_percent_is_still_modulo_when_it_is_modulo():
    assert calculate("10 % 3")["value"] == 1
    assert calculate("10%3")["value"] == 1


def test_the_result_reads_back_as_a_sentence():
    """The activity log and the model both read the 'result' key."""
    assert calculate("2 + 2")["result"] == "2 + 2 = 4"


# ── it cannot be used for anything else ───────────────────

@pytest.mark.parametrize("hostile", [
    '__import__("os").system("ls")',
    'open("/etc/passwd").read()',
    "().__class__.__bases__",
    "exec('x=1')",
    "eval('1+1')",
    "globals()",
    "[].__class__",
    "lambda: 1",
    "x = 5",
    "print(1)",
    "1 if True else 2",
    "[i for i in range(10)]",
])
def test_only_arithmetic_gets_through(hostile):
    """Not eval(). The expression is parsed and walked against a whitelist, so
    an expression arriving from a model — or from a document a model read —
    cannot reach an attribute, a name, or the interpreter."""
    result = calculate(hostile)
    assert result["status"] == "error", f"{hostile!r} was evaluated: {result}"


def test_a_runaway_exponent_is_refused_rather_than_attempted():
    """2**10**9 is eleven characters and would try to allocate more memory
    than the machine has."""
    result = calculate("2 ** 10 ** 9")
    assert result["status"] == "error"
    assert "too large" in result["error"]


def test_dividing_by_zero_is_explained():
    result = calculate("1 / 0")
    assert result["status"] == "error"
    assert "zero" in result["error"]


def test_an_incomplete_expression_says_so():
    result = calculate("2 +")
    assert result["status"] == "error"
    assert result["retry_safe"] is True


def test_an_empty_expression_is_refused():
    assert calculate("")["status"] == "error"
    assert calculate("   ")["status"] == "error"


def test_an_unknown_function_names_the_ones_that_exist():
    result = calculate("median([1,2,3])")
    assert result["status"] == "error"
    assert "sum" in result["error"] and "round" in result["error"]


def test_a_bare_name_is_refused_clearly():
    result = calculate("total + 5")
    assert result["status"] == "error"
    assert "total" in result["error"]


def test_pi_and_e_are_available():
    assert round(calculate("pi")["value"], 5) == 3.14159


def test_every_error_is_retryable():
    """Every failure here is the expression's fault and a different
    expression may well work, so none of them should read as a dead end."""
    for bad in ("2 +", "median(1)", "1/0", "", "open('x')"):
        result = calculate(bad)
        assert result["status"] == "error"
        assert result["retry_safe"] is True, bad


# ── the runtime surface ───────────────────────────────────

def test_it_is_declared_and_ungated():
    """Pure computation with no side effect: gating it would train the user to
    click through prompts that never matter."""
    from brain.core_tools import TOOL_DECLARATIONS, needs_confirmation

    assert "calculate" in {d.name for d in TOOL_DECLARATIONS}
    assert not needs_confirmation("calculate", {"expression": "1+1"})


def test_the_runtime_routes_it():
    from brain.core_runtime import CoreRuntime

    result = CoreRuntime()._execute_tool("calculate", {"expression": "2417 + 3168 + 912"})
    assert result["status"] == "success"
    assert result["value"] == 6497


def test_the_runtime_reports_a_bad_expression_without_raising():
    from brain.core_runtime import CoreRuntime

    result = CoreRuntime()._execute_tool("calculate", {"expression": "open('x')"})
    assert result["status"] == "error"
