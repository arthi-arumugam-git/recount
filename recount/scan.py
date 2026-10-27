"""Walk a repository and run every detector. Reads files only; runs nothing."""

from __future__ import annotations

from pathlib import Path

from .core import Finding, is_test_path, parse
from .detectors import cache_tokens, dropped_cost, ignored_config, legal_value, silent_zero

SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "env", "site-packages", "__pycache__", "build", "dist",
             ".tox", ".mypy_cache", ".pytest_cache", "vendor", "third_party", ".next", "target"}
# Code that ships to users. Example, script, docs and notebook folders are skipped by default,
# because a wrong number there is rarely one anybody acts on.
NOT_SHIPPED = {"examples", "example", "scripts", "docs", "doc", "cookbook", "cookbooks", "notebooks",
               "tutorials", "samples", "demo", "demos"}
MAX_BYTES = 1_000_000
PY_DETECTORS = (silent_zero, legal_value, ignored_config, dropped_cost)


def scan_file(full: Path, rel: str, include_tests: bool = False) -> list[Finding]:
    if not include_tests and is_test_path(rel):
        return []
    out: list[Finding] = []
    if full.suffix in cache_tokens.SUFFIXES:
        try:
            out += cache_tokens.check_path(str(full), rel)
        except Exception:  # a vendored rule failing on one file must not stop the scan
            pass
    if full.suffix == ".py":
        try:
            source = full.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return out
        tree = parse(source, rel)
        if tree is None:
            return out
        lines = source.splitlines()
        for det in PY_DETECTORS:
            out += det.check(tree, rel, lines)
    return out


def iter_files(root: Path, everything: bool = False):
    root = root.resolve()
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        if not everything and any(part.lower() in NOT_SHIPPED for part in rel.parts[:-1]):
            continue
        if p.is_symlink() or not p.is_file():
            continue
        if p.suffix not in cache_tokens.SUFFIXES and p.suffix != ".py":
            continue
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
        except OSError:
            continue
        yield p, rel.as_posix()


def scan(root: str | Path, include_tests: bool = False, only: list[str] | None = None,
         everything: bool = False) -> list[Finding]:
    root = Path(root)
    findings: list[Finding] = []
    for full, rel in iter_files(root, everything):
        if only is not None and rel not in only:
            continue
        findings += scan_file(full, rel, include_tests)
    # One finding per (file, line, rule).
    seen, unique = set(), []
    for f in sorted(findings, key=lambda f: (f.file, f.line, f.rule)):
        key = (f.file, f.line, f.rule)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique
