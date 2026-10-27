"""Class 11, config accepted and silently ignored.

A public parameter is accepted and never used, so setting it does nothing.

    def __init__(self, api_key, base_path=BASE_URL, timeout=HTTPX_TIME_OUT):   # okareo#261
        self.client = Client(base_url=base_path)                               # timeout never used
    def _get_statistics(..., force_download=False): ... snapshot_download(...)  # unsloth#8906
"""

from __future__ import annotations

import ast
import re

from ..core import Finding, enclosing_class, is_test_path, snippet

RULE = "parameter-accepted-and-ignored"

# Parameters whose silent absence changes behaviour someone relies on.
CONFIG = re.compile(
    r"^(timeout|request_timeout|connect_timeout|read_timeout|force_download|max_retries|retries|"
    r"temperature|top_p|top_k|seed|max_tokens|max_new_tokens|max_output_tokens|frequency_penalty|"
    r"presence_penalty|verify|verify_ssl|ssl|proxies|proxy|cache_dir|revision|token|base_url|api_base|"
    r"organization|n|stop|stream|batch_size|num_workers|device|dtype|trust_remote_code|strict)$"
)


def _trivial_body(fn) -> bool:
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    if not body:
        return True
    if len(body) == 1:
        s = body[0]
        if isinstance(s, ast.Pass):
            return True
        if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and s.value.value is Ellipsis:
            return True
        if isinstance(s, ast.Raise):
            return True
        if isinstance(s, ast.Return) and (s.value is None or isinstance(s.value, ast.Constant)):
            return True
    return False


def _decorator_names(fn) -> set[str]:
    out = set()
    for d in fn.decorator_list:
        target = d.func if isinstance(d, ast.Call) else d
        out.add(getattr(target, "id", getattr(target, "attr", "")))
    return out


def check(tree: ast.AST, path: str, lines: list[str]) -> list[Finding]:
    if is_test_path(path):
        return []
    found: list[Finding] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name.startswith("__") and fn.name != "__init__":
            continue
        # Methods that implement an interface ignore parameters by design; only
        # constructors and module-level functions promise to honour what they accept.
        cls = enclosing_class(fn)
        if cls is not None and fn.name != "__init__":
            continue
        if cls is not None and fn.name == "__init__" and fn.args.kwarg is not None:
            continue
        if _trivial_body(fn) or _decorator_names(fn) & {"abstractmethod", "overload", "override"}:
            continue
        # Anything that forwards locals() or **kwargs wholesale may use the parameter indirectly.
        body_src = ast.dump(ast.Module(body=fn.body, type_ignores=[]))
        if "locals" in body_src or "vars" in body_src or "signature" in body_src:
            continue
        params = [*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs]
        used = {n.id for n in ast.walk(ast.Module(body=fn.body, type_ignores=[])) if isinstance(n, ast.Name)}
        for p in params:
            if p.arg in ("self", "cls") or not CONFIG.match(p.arg) or p.arg in used:
                continue
            found.append(Finding(
                RULE, 11, path, fn.lineno, fn.lineno,
                f"{fn.name}() accepts '{p.arg}' and never uses it, so setting it changes nothing.",
                snippet(lines, fn), "medium"))
    return found
