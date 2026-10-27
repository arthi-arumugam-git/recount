"""Rediscovery benchmark: does Recount find Arthi's real bugs without being told where?

For each merged fix (bench/fixes.json, built by bench/fetch.py):
  before = the code the fix was written against (the bug is present)
  after  = the fix
Each file the fix touched is scanned at both commits.

  caught       a finding lands inside the lines the fix changed, at 'before'
  same file    a finding is in the changed file but not on the changed lines
  missed       nothing on the changed lines
  fix flagged  a finding is still on the changed lines at 'after' (a false alarm on correct code)

Only the files each fix touched are scanned; whole-repository noise is measured separately.
Nothing in the scanned repositories is run.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from recount.scan import scan  # noqa: E402

REPOS = Path(os.environ.get("AUDIT_REPOS", "/tmp/audit-repos"))
FIXES = Path(__file__).resolve().parent / "fixes.json"
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", re.M)
TOL = 2  # lines of slack around a hunk


def git(repo_dir: Path, *args) -> str:
    return subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True, text=True,
                          timeout=600).stdout


def hunks(repo_dir: Path, before: str, after: str, path: str):
    diff = git(repo_dir, "diff", "-U0", before, after, "--", path)
    old, new = [], []
    for m in HUNK.finditer(diff):
        a, b = int(m.group(1)), int(m.group(2) or 1)
        c, d = int(m.group(3)), int(m.group(4) or 1)
        old.append((a - TOL, a + max(b, 1) - 1 + TOL))
        new.append((c - TOL, c + max(d, 1) - 1 + TOL))
    return old, new


def materialise(repo_dir: Path, commit: str, files: list[str], dest: Path) -> list[str]:
    present = []
    for f in files:
        try:
            content = git(repo_dir, "show", f"{commit}:{f}")
        except subprocess.CalledProcessError:
            continue  # file added or deleted by the fix
        p = dest / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        present.append(f)
    return present


def within(line: int, ranges) -> bool:
    return any(lo <= line <= hi for lo, hi in ranges)


def main():
    fixes = json.loads(FIXES.read_text())
    rows = []
    for e in fixes:
        row = {"repo": e["repo"], "pr": e["pr"], "class": e["class"], "title": e["title"]}
        if e.get("error") or not e.get("files"):
            row["result"] = "not recoverable"
            rows.append(row)
            continue
        repo_dir = REPOS / e["repo"].replace("/", "__")
        code_files = [f for f in e["files"]
                      if re.search(r"\.(py|ts|tsx|js|mjs)$", f) and not re.search(r"(^|/)(tests?|__tests__)/|test_|\.test\.", f)]
        if not code_files:
            row["result"] = "no source change (tests, docs or data only)"
            rows.append(row)
            continue
        with tempfile.TemporaryDirectory() as tb, tempfile.TemporaryDirectory() as ta:
            got_b = materialise(repo_dir, e["before"], code_files, Path(tb))
            got_a = materialise(repo_dir, e["after"], code_files, Path(ta))
            fb = scan(tb, only=got_b)
            fa = scan(ta, only=got_a)
        caught, same_file, fix_flagged = [], [], []
        for f in code_files:
            old, new = hunks(repo_dir, e["before"], e["after"], f)
            for x in fb:
                if x.file == f:
                    (caught if within(x.line, old) else same_file).append(x)
            for x in fa:
                if x.file == f and within(x.line, new):
                    fix_flagged.append(x)
        # A finding the fix made disappear: same file and rule, fewer of them after the fix.
        from collections import Counter
        cb = Counter((x.file, x.rule) for x in fb)
        ca = Counter((x.file, x.rule) for x in fa)
        resolved = [k for k in cb if cb[k] > ca.get(k, 0)]
        row.update(
            files=code_files,
            resolved_by_fix=resolved,
            caught=[(x.file, x.line, x.rule) for x in caught],
            same_file_other=[(x.file, x.line, x.rule) for x in same_file],
            fix_flagged=[(x.file, x.line, x.rule) for x in fix_flagged],
            result=("caught on the fixed lines" if caught else
                    "caught in the fixed file" if resolved else "missed"),
        )
        rows.append(row)
        print(f"{e['repo']}#{e['pr']:<6} class={e['class']}  {row['result']:<27} "
              f"caught={len(caught)} other={len(same_file)} fix_flagged={len(fix_flagged)}", flush=True)
    out = ROOT / "bench" / "replay.json"
    out.write_text(json.dumps(rows, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
