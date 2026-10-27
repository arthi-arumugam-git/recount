"""Class 1, cache-token exclusion: Arthi Arumugam's cachecheck rules (MIT), vendored.

cachecheck reads Python, TypeScript and other languages, so this is the one
detector that also covers non-Python files.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from ..core import Finding

_SPEC = importlib.util.spec_from_file_location(
    "recount._vendor_cachecheck", Path(__file__).resolve().parent.parent / "_vendor" / "cachecheck_checker.py")
_cc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_cc)  # type: ignore[union-attr]

SUFFIXES = tuple(_cc.SUFFIXES)


def check_path(full_path: str, rel_path: str) -> list[Finding]:
    out = []
    for f in _cc.check_file(full_path) or []:
        line = int(f.get("line", 0) or 0)
        out.append(Finding(
            rule=str(f.get("rule", "cache-token")), bug_class=1, file=rel_path, line=line, end_line=line,
            message=str(f.get("why", "Cache tokens left out of the token accounting.")),
            snippet=str(f.get("evidence", ""))[:200], confidence="high"))
    return out
