"""Class 2, a guard that filters a legal value.

A truthiness or type check meant to skip missing data also skips a legal value
(0, an int cost), and a default or nothing takes its place.

    if response.temperature:                  # okareo#260: temperature=0 came back as 0.6
        self.temperature = response.temperature
    t = kwargs.get("temperature") or 0.7       # temperature=0 becomes 0.7
    if isinstance(usage.cost, float): ...      # langfuse#1781: an int cost is dropped
"""

from __future__ import annotations

import ast

from ..core import NUMERIC_NAME, Finding, enclosing_function, is_const_number, is_test_path, leaf_name, same_expr, snippet

RULE_TRUTHY_GUARD = "truthiness-guard-drops-zero"
RULE_OR_DEFAULT = "or-default-replaces-zero"
RULE_FLOAT_ONLY = "isinstance-float-drops-int"


def _numeric(node: ast.AST) -> str | None:
    name = leaf_name(node)
    return name if name and NUMERIC_NAME.search(name) else None


def _int_handled_nearby(call: ast.Call, target: ast.AST) -> bool:
    """True when the enclosing function also checks isinstance(<same expr>, int)."""
    fn = enclosing_function(call) or getattr(call, "_parent", None)
    if fn is None:
        return False
    for n in ast.walk(fn):
        if n is not call and isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "isinstance" \
                and len(n.args) == 2 and same_expr(n.args[0], target):
            t = n.args[1]
            names = {getattr(e, "id", None) for e in (t.elts if isinstance(t, ast.Tuple) else [t])}
            if "int" in names:
                return True
    return False


def check(tree: ast.AST, path: str, lines: list[str]) -> list[Finding]:
    if is_test_path(path):
        return []
    found: list[Finding] = []

    def add(rule, node, message, confidence):
        found.append(Finding(rule, 2, path, node.lineno, getattr(node, "end_lineno", node.lineno),
                             message, snippet(lines, node), confidence))

    for node in ast.walk(tree):
        # if x.temperature:  self.temperature = x.temperature
        if isinstance(node, ast.If) and not isinstance(node.test, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
            name = _numeric(node.test)
            if name and any(
                isinstance(stmt, ast.Assign) and same_expr(stmt.value, node.test) for stmt in node.body
            ):
                add(RULE_TRUTHY_GUARD, node,
                    f"'if {name}:' is false for 0, so a legal {name} of 0 is never copied and the old or "
                    f"default value stays. Use 'is not None'.", "high")

        # x = something.temperature or 0.7   (a non-zero default)
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and len(node.values) == 2:
            left, right = node.values
            name = _numeric(left)
            if name and is_const_number(right) and right.value != 0:
                add(RULE_OR_DEFAULT, node,
                    f"'{name} or {right.value!r}' turns a legal {name} of 0 into {right.value!r}. "
                    f"Use '{right.value!r} if {name} is None else {name}'.", "high")

        # isinstance(cost, float) with no int alongside
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "isinstance" \
                and len(node.args) == 2:
            target, types = node.args
            name = _numeric(target)
            if not name:
                continue
            listed = {getattr(t, "id", None) for t in (types.elts if isinstance(types, ast.Tuple) else [types])}
            if "float" in listed and "int" not in listed and not listed & {"Number", "Real", "numbers"} \
                    and not _int_handled_nearby(node, target):
                add(RULE_FLOAT_ONLY, node,
                    f"isinstance({name}, float) is False for an int, so an integer {name} (for example 0 "
                    f"or a whole-dollar cost) is treated as missing. Accept (int, float) and exclude bool.",
                    "medium")
    return found
