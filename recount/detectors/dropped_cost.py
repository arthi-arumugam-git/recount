"""Class 10, missing price data and cost silently dropped.

A price lookup that fails turns into 0 or nothing instead of a visible gap.

    price = PRICES.get(model, 0)            # an unknown model costs nothing
    try:
        cost = calc_cost(...)
    except Exception:
        cost = None                         # logfire#2162 shape: tokens recorded, cost column empty
"""

from __future__ import annotations

import ast
import re

from ..core import Finding, is_test_path, is_zero, snippet

RULE_ZERO_PRICE = "unknown-model-priced-at-zero"
RULE_SWALLOWED = "cost-error-swallowed"

# "rate" only as a whole word part (input_rate, rate_card), never inside generate or iterate.
PRICEY = re.compile(r"price|pricing|cost|tariff|(^|_)rates?(_|$)", re.I)


def _name(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def check(tree: ast.AST, path: str, lines: list[str]) -> list[Finding]:
    if is_test_path(path):
        return []
    found: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" \
                and len(node.args) == 2 and is_zero(node.args[1]) and PRICEY.search(_name(node.func.value)) \
                and not (isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            # A literal key ("input_cost_per_token") reads a field of a price record that was
            # already found; the bug shape is a lookup keyed by a model name held in a variable.
            found.append(Finding(
                RULE_ZERO_PRICE, 10, path, node.lineno, node.end_lineno or node.lineno,
                f"A model missing from '{_name(node.func.value)}' is priced at 0, so its spend disappears "
                "instead of showing up as unpriced.", snippet(lines, node), "high"))

        if isinstance(node, ast.Try):
            try_names = {getattr(n, "id", getattr(n, "attr", "")) for n in ast.walk(ast.Module(body=node.body, type_ignores=[]))
                         if isinstance(n, (ast.Name, ast.Attribute))}
            if not any(PRICEY.search(n or "") for n in try_names):
                continue
            for handler in node.handlers:
                broad = handler.type is None or _name(handler.type) in {"Exception", "BaseException"}
                body = handler.body
                silent = all(
                    isinstance(s, ast.Pass)
                    or (isinstance(s, ast.Return) and (s.value is None or isinstance(s.value, ast.Constant)))
                    or (isinstance(s, ast.Assign) and isinstance(s.value, ast.Constant)
                        and any(PRICEY.search(_name(t)) for t in s.targets))
                    or (isinstance(s, ast.Continue))
                    for s in body
                )
                logs = any(isinstance(n, ast.Call) and _name(getattr(n, "func", None)) in
                           {"warning", "warn", "error", "exception", "info", "debug", "log"}
                           for n in ast.walk(ast.Module(body=body, type_ignores=[])))
                if broad and silent and not logs:
                    found.append(Finding(
                        RULE_SWALLOWED, 10, path, handler.lineno, handler.end_lineno or handler.lineno,
                        "A failed cost or price calculation is swallowed without a log, so spans keep their "
                        "token counts with an empty or zero cost.", snippet(lines, handler), "medium"))
    return found
