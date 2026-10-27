"""Class 3, silent-zero metrics (and the class 4 divisor fallback that causes them).

A metric that had nothing to score returns a number on its own scale (usually 0.0)
instead of nan or an error, so "nothing was measured" reads as a real result.

Shapes found by hand in inspect_evals, deepeval and trulens:

    return confident / right if right > 0 else 0.0            # sycophancy, inspect_evals#2036
    avg = sum(v) / len(v) if v else 0.0                        # stereoset, inspect_evals#2123
    divisor = len(scores) if len(scores) > 0 else 1            # deepeval#2968
    if not scores: return 0.0                                  # agentharm, inspect_evals#2174
    return total / max(len(scores), 1)
"""

from __future__ import annotations

import ast

from ..core import Finding, enclosing_function, in_metric_context, is_const_number, is_zero, names_in, snippet

RULE_GUARDED_DIVISION = "guarded-division-returns-number"
RULE_DIVISOR_FALLBACK = "divisor-fallback-to-one"
RULE_EMPTY_RETURNS_NUMBER = "empty-input-returns-number"
RULE_MAX_ONE = "max-one-denominator"


def _tests_emptiness_of(test: ast.AST) -> set[str]:
    """Names whose emptiness or zero-ness this condition checks."""
    out: set[str] = set()
    t = test
    if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not):
        t = t.operand
    if isinstance(t, (ast.Name, ast.Attribute)):
        out |= names_in(t)
    elif isinstance(t, ast.Call) and isinstance(t.func, ast.Name) and t.func.id == "len" and t.args:
        out |= names_in(t.args[0])
    elif isinstance(t, ast.Compare) and len(t.comparators) == 1:
        left, right = t.left, t.comparators[0]
        if is_zero(right) or is_zero(left):
            other = left if is_zero(right) else right
            if isinstance(other, ast.Call) and isinstance(other.func, ast.Name) and other.func.id == "len" and other.args:
                out |= names_in(other.args[0])
            else:
                out |= names_in(other)
    return out


def _denominator(node: ast.AST) -> ast.AST | None:
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv)):
        return node.right
    return None


def _contains_division_by(node: ast.AST, names: set[str]) -> bool:
    for n in ast.walk(node):
        den = _denominator(n)
        if den is not None and names & names_in(den):
            return True
    return False


def _is_number_return(value: ast.AST | None) -> bool:
    return value is not None and is_const_number(value)


def check(tree: ast.AST, path: str, lines: list[str]) -> list[Finding]:
    found: list[Finding] = []

    def add(rule, node, message, confidence):
        found.append(Finding(rule, 3, path, node.lineno, getattr(node, "end_lineno", node.lineno),
                             message, snippet(lines, node), confidence))

    for node in ast.walk(tree):
        # a / b if b else 0.0   (either branch order)
        if isinstance(node, ast.IfExp):
            for value, fallback, cond_true_means_nonempty in ((node.body, node.orelse, True),
                                                              (node.orelse, node.body, False)):
                if not is_const_number(fallback):
                    continue
                checked = _tests_emptiness_of(node.test)
                if not checked:
                    continue
                negated = isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not)
                if cond_true_means_nonempty == negated and not isinstance(node.test, ast.Compare):
                    continue
                if _contains_division_by(value, checked) and in_metric_context(path, node):
                    add(RULE_GUARDED_DIVISION, node,
                        f"Returns {fallback.value!r} when there is nothing to divide by, so 'nothing was "
                        "measured' reads as a real score. Return float('nan') (or raise) instead.",
                        "high" if is_zero(fallback) else "medium")
                    break

            # divisor = len(x) if len(x) > 0 else 1
            if isinstance(node.orelse, ast.Constant) and node.orelse.value == 1 \
                    and isinstance(node.body, ast.Call) and isinstance(node.body.func, ast.Name) \
                    and node.body.func.id == "len" and in_metric_context(path, node):
                add(RULE_DIVISOR_FALLBACK, node,
                    "Falls back to a divisor of 1 when the collection is empty, so the score becomes 0 "
                    "rather than undefined.", "medium")

        # total / max(len(x), 1)
        den = _denominator(node)
        if den is not None and isinstance(den, ast.Call) and isinstance(den.func, ast.Name) \
                and den.func.id == "max" and any(isinstance(a, ast.Constant) and a.value == 1 for a in den.args) \
                and in_metric_context(path, node):
            add(RULE_MAX_ONE, node,
                "Divides by max(n, 1), so an empty input reports 0 instead of undefined.", "medium")

        # if not xs: return 0.0   ...later: something / len(xs)
        if isinstance(node, ast.If) and node.body and isinstance(node.body[0], ast.Return) \
                and _is_number_return(node.body[0].value):
            checked = _tests_emptiness_of(node.test)
            negated = isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not)
            is_eq_zero = isinstance(node.test, ast.Compare) and isinstance(node.test.ops[0], (ast.Eq, ast.LtE))
            if not checked or not (negated or is_eq_zero):
                continue
            # 'if precision + recall == 0: return 0.0' is the defined limit of an F-score,
            # not an empty input.
            if isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.BinOp) \
                    and isinstance(node.test.left.op, ast.Add):
                continue
            fn = enclosing_function(node)
            if fn is None or not in_metric_context(path, node):
                continue
            if _contains_division_by(fn, checked) or any(
                    isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))
                    and getattr(n.func, "id", getattr(n.func, "attr", "")) in {"mean", "average", "fmean"}
                    for n in ast.walk(fn)):
                add(RULE_EMPTY_RETURNS_NUMBER, node,
                    f"Returns {node.body[0].value.value!r} when there is nothing to score, which looks the "
                    "same as a real result. Return float('nan') (or raise) instead.",
                    "high" if is_zero(node.body[0].value) else "medium")
    return found
