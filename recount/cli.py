"""recount: find AI numbers that are silently wrong.

  recount PATH            list findings; exit code 1 if any (for CI)
  recount PATH --json     machine-readable output
  recount PATH --tests    include test files

Reads source only. Nothing in the scanned code is imported or run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .scan import scan

CLASS_NAMES = {
    1: "cache tokens left out", 2: "a guard drops a legal 0", 3: "silent zero",
    10: "cost silently dropped", 11: "setting accepted and ignored",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="recount", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--tests", action="store_true", help="also scan test files")
    ap.add_argument("--everything", action="store_true",
                    help="also scan examples, scripts, docs and notebooks folders")
    ap.add_argument("--min-confidence", choices=["medium", "high"], default="medium")
    args = ap.parse_args(argv)

    root = Path(args.path)
    if not root.is_dir():
        print(f"recount: not a directory: {root}", file=sys.stderr)
        return 2
    findings = scan(root, include_tests=args.tests, everything=args.everything)
    if args.min_confidence == "high":
        findings = [f for f in findings if f.confidence == "high"]

    if args.json:
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        for f in findings:
            print(f"{f.file}:{f.line}  [{CLASS_NAMES.get(f.bug_class, f.bug_class)}, {f.confidence}] {f.rule}")
            print(f"    {f.snippet}")
            print(f"    {f.message}")
        print(f"\n{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
