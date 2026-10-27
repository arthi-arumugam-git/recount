"""Shared types and helpers for Recount's detectors.

Every detector reads Python source with the standard ast module. Nothing in a
scanned repository is imported or executed.
"""

from __future__ import annotations

import ast
import re
import warnings
from dataclasses import asdict, dataclass

# Words that mark code which produces a number someone will act on.
METRIC_WORDS = re.compile(
    r"metric|scor|accura|precision|recall|\bf1\b|_f1|f1_|mean|average|avg|rate|ratio|"
    r"eval|bench|judge|grade|pass_at|pass@|percent|stat|aggregat|reward",
    re.I,
)
# Names that hold numeric values where 0 is legal and meaningful.
NUMERIC_NAME = re.compile(
    r"(^|_)(temperature|temp|top_p|seed|cost|price|tokens|score|threshold|max_retries|"
    r"frequency_penalty|presence_penalty|penalty|logprobs|weight|budget|amount)$",
    re.I,
)


@dataclass
class Finding:
    rule: str
    bug_class: int          # wrong-numbers taxonomy id
    file: str
    line: int
    end_line: int
    message: str
    snippet: str
    confidence: str         # "high" or "medium"

    def to_dict(self) -> dict:
        return asdict(self)


def parse(source: str, filename: str) -> ast.AST | None:
    try:
        with warnings.catch_warnings():
            # Invalid escapes in the scanned code are its business, not ours.
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError):
        return None
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child._parent = node  # type: ignore[attr-defined]
    return tree


def parent(node: ast.AST) -> ast.AST | None:
    return getattr(node, "_parent", None)


def enclosing_function(node: ast.AST) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    cur = parent(node)
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur
        cur = parent(cur)
    return None


def enclosing_class(node: ast.AST) -> ast.ClassDef | None:
    cur = parent(node)
    while cur is not None:
        if isinstance(cur, ast.ClassDef):
            return cur
        cur = parent(cur)
    return None


def snippet(source_lines: list[str], node: ast.AST) -> str:
    line = source_lines[node.lineno - 1] if 0 < node.lineno <= len(source_lines) else ""
    return line.strip()[:200]


def is_zero(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and not isinstance(node.value, bool) \
        and isinstance(node.value, (int, float)) and node.value == 0


def is_const_number(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and not isinstance(node.value, bool) \
        and isinstance(node.value, (int, float))


def names_in(node: ast.AST) -> set[str]:
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def leaf_name(node: ast.AST) -> str | None:
    """The last name in a.b.c, a["c"], or a.get("c")."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        sl = node.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            return sl.value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" \
            and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value
    return None


def same_expr(a: ast.AST, b: ast.AST) -> bool:
    return ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False)


def in_metric_context(path: str, node: ast.AST) -> bool:
    """True when the file path or the enclosing function or class name reads as metric code."""
    if METRIC_WORDS.search(path):
        return True
    fn = enclosing_function(node)
    if fn is not None and METRIC_WORDS.search(fn.name):
        return True
    cls = enclosing_class(node)
    return cls is not None and bool(METRIC_WORDS.search(cls.name))


def is_test_path(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    name = p.rsplit("/", 1)[-1]
    return (
        "/tests/" in f"/{p}" or "/test/" in f"/{p}" or name.startswith("test_")
        or name.endswith("_test.py") or name == "conftest.py"
    )
