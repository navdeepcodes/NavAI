"""Arithmetic Mike does not have to do in its head.

Measured, on a six-workbook task: every file was read correctly, every cell
was written correctly, the goal survived fifteen turns without drifting — and
the total of 2417 + 3168 + 912 came out as 6500 instead of 6497, on the very
first workbook, and then propagated into the summary consistently enough to
look right. Nothing in the runtime could have caught it, because nothing in
the runtime could add.

This is not a workflow step and it decides nothing. It evaluates an
expression and returns the number. The model chooses when a figure matters
enough to check, exactly as it chooses when to read a file.

Deliberately not eval(). The expression is parsed to an AST and walked
against a whitelist, so a string arriving from a model — or from a document a
model read — cannot reach an attribute, a name, a call to anything but the
handful of functions below, or any part of the interpreter.
"""
from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any

MAX_EXPRESSION = 2000

# Guards against a single expression burning the machine: 2 ** 10 ** 9 is
# eleven characters and would try to allocate more memory than exists.
MAX_EXPONENT = 1000

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}

_FUNCTIONS = {
    "sum": lambda *a: sum(a[0]) if len(a) == 1 and isinstance(a[0], (list, tuple)) else sum(a),
    "min": lambda *a: min(a[0]) if len(a) == 1 and isinstance(a[0], (list, tuple)) else min(a),
    "max": lambda *a: max(a[0]) if len(a) == 1 and isinstance(a[0], (list, tuple)) else max(a),
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "floor": math.floor,
    "ceil": math.ceil,
}

_CONSTANTS = {"pi": math.pi, "e": math.e}


# A comma between a digit and exactly three more digits: a thousands
# separator, not a list separator.
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")

# A percent sign closing a number and not being used as modulo — nothing
# numeric follows it.
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%(?!\s*[\d(.])")


class CalculationError(ValueError):
    """The expression is not arithmetic this can evaluate."""


def _evaluate(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalculationError(f"{node.value!r} is not a number.")
        return node.value

    if isinstance(node, ast.BinOp):
        handler = _BINARY.get(type(node.op))
        if not handler:
            raise CalculationError(f"{type(node.op).__name__} is not allowed here.")
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise CalculationError(
                f"An exponent of {right} is too large to evaluate."
            )
        try:
            return handler(left, right)
        except ZeroDivisionError:
            raise CalculationError("That divides by zero.") from None

    if isinstance(node, ast.UnaryOp):
        handler = _UNARY.get(type(node.op))
        if not handler:
            raise CalculationError(f"{type(node.op).__name__} is not allowed here.")
        return handler(_evaluate(node.operand))

    if isinstance(node, (ast.List, ast.Tuple)):
        return [_evaluate(item) for item in node.elts]

    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise CalculationError(
            f"{node.id!r} is not a number. Use digits, not names for values."
        )

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            name = getattr(node.func, "id", "that")
            raise CalculationError(
                f"{name} is not available. You can use: "
                + ", ".join(sorted(_FUNCTIONS))
            )
        if node.keywords:
            raise CalculationError("Keyword arguments are not supported.")
        return _FUNCTIONS[node.func.id](*[_evaluate(a) for a in node.args])

    raise CalculationError(
        f"{type(node).__name__} is not arithmetic. Give a plain expression "
        "like 2417 + 3168 + 912."
    )


def calculate(expression: str) -> dict[str, Any]:
    """Evaluate one arithmetic expression exactly."""
    text = (expression or "").strip()
    if not text:
        return {"status": "error", "retry_safe": True,
                "error": "No expression was given."}
    if len(text) > MAX_EXPRESSION:
        return {"status": "error", "retry_safe": True,
                "error": f"That expression is too long ({len(text)} characters)."}

    # A model writing arithmetic for a person naturally writes 1,234 and 50%.
    # Rejecting those teaches nothing; they have exact meanings. Both
    # rewrites are narrow on purpose: a blunt comma strip turned sum([1,2,3])
    # into sum([123]), and a blunt percent rewrite would break modulo.
    cleaned = _THOUSANDS.sub("", text)
    cleaned = _PERCENT.sub(lambda m: f"({m.group(1)}/100)", cleaned)

    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as exc:
        return {"status": "error", "retry_safe": True,
                "error": f"{text!r} is not a complete expression ({exc.msg})."}

    try:
        value = _evaluate(tree)
    except CalculationError as exc:
        return {"status": "error", "retry_safe": True, "error": str(exc)}
    except (OverflowError, ValueError) as exc:
        return {"status": "error", "retry_safe": True,
                "error": f"That could not be evaluated: {exc}"}

    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, float):
        value = round(value, 10)

    return {
        "status": "success",
        "expression": text,
        "value": value,
        "result": f"{text} = {value}",
    }
