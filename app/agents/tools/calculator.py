"""Safe arithmetic calculator for agent use.

Uses Python's ast module to parse and evaluate mathematical expressions
without allowing arbitrary code execution. Only numeric operations and a
curated set of math functions are permitted.

Intended for financial calculations: budget variances, donation totals,
grant utilisation percentages, TDS amounts, etc.
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any, Union

# Whitelist of safe operators
_OPERATORS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Whitelist of safe math functions accessible in expressions
_SAFE_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "sqrt": math.sqrt,
    "ceil": math.ceil,
    "floor": math.floor,
    "log": math.log,
    "log10": math.log10,
    "pow": math.pow,
    "pi": math.pi,
    "e": math.e,
    "int": int,
    "float": float,
}

_Number = Union[int, float]


class _SafeEvaluator(ast.NodeVisitor):
    """AST visitor that evaluates only safe numeric expressions."""

    def visit_Expression(self, node: ast.Expression) -> _Number:
        return self.visit(node.body)

    def visit_BinOp(self, node: ast.BinOp) -> _Number:
        op_fn = _OPERATORS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        left = self.visit(node.left)
        right = self.visit(node.right)

        # Guard against division by zero
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise ValueError("Division by zero")

        # Guard against unreasonably large exponents
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("Exponent too large (max 1000)")

        return op_fn(left, right)  # type: ignore[operator]

    def visit_UnaryOp(self, node: ast.UnaryOp) -> _Number:
        op_fn = _OPERATORS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op_fn(self.visit(node.operand))  # type: ignore[operator]

    def visit_Call(self, node: ast.Call) -> _Number:
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only named functions are allowed")
        fn = _SAFE_FUNCTIONS.get(node.func.id)
        if fn is None:
            raise ValueError(f"Function '{node.func.id}' is not allowed. "
                             f"Allowed: {', '.join(sorted(_SAFE_FUNCTIONS))}")
        args = [self.visit(a) for a in node.args]
        return fn(*args)

    def visit_Constant(self, node: ast.Constant) -> _Number:
        if not isinstance(node.value, (int, float)):
            raise ValueError(f"Only numeric constants are allowed, got: {type(node.value).__name__}")
        return node.value

    # Allow bare names only for math constants (pi, e)
    def visit_Name(self, node: ast.Name) -> _Number:
        if node.id not in _SAFE_FUNCTIONS:
            raise ValueError(f"Unknown name: '{node.id}'")
        val = _SAFE_FUNCTIONS[node.id]
        if not isinstance(val, (int, float)):
            raise ValueError(f"'{node.id}' is a function, not a constant")
        return val

    def generic_visit(self, node: ast.AST) -> Any:  # type: ignore[override]
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def calculate(expression: str) -> str:
    """Evaluate a mathematical expression and return a formatted string result.

    Args:
        expression: A math expression string, e.g. "50000 * 0.10 + 1200".

    Returns:
        A human-readable result string, e.g. "Result: 6200.0"

    Raises:
        ValueError: If the expression is invalid or uses unsupported operations.
    """
    # Hard limit on expression length to prevent DOS via deeply nested expressions
    if len(expression) > 500:
        raise ValueError("Expression too long (max 500 characters)")

    expression = expression.strip()

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid expression syntax: {exc}") from exc

    evaluator = _SafeEvaluator()
    result = evaluator.visit(tree)

    # Format: integers without decimal, floats with up to 6 significant digits
    if isinstance(result, float) and result.is_integer():
        formatted = f"{int(result):,}"
    elif isinstance(result, float):
        # Round to avoid floating-point noise like 0.1 + 0.2 = 0.30000000000000004
        formatted = f"{round(result, 6):,}"
    else:
        formatted = f"{result:,}"

    return f"Result: {formatted}"
