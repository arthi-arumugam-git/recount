"""Scan many public repositories at their default branch, read only.

Writes bench/sweep.json: per repository, the commit scanned and every finding.
Nothing is run, pushed or reported anywhere.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from recount.scan import scan  # noqa: E402

WORK = Path(os.environ.get("SWEEP_DIR", "/tmp/sweep-repos"))
ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}


def main(targets: Path):
    WORK.mkdir(parents=True, exist_ok=True)
    out = []
    for repo in [l.strip() for l in targets.read_text().splitlines() if l.strip() and not l.startswith("#")]:
        dest = WORK / repo.replace("/", "__")
        try:
            if not dest.exists():
                subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--filter=blob:limit=1m",
                                f"https://github.com/{repo}.git", str(dest)],
                               check=True, capture_output=True, timeout=900, env=ENV)
            commit = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], check=True,
                                    capture_output=True, text=True).stdout.strip()
            findings = scan(dest)
            out.append({"repo": repo, "commit": commit, "findings": [f.to_dict() for f in findings]})
            print(f"{repo:45} {commit[:8]} findings={len(findings)}", flush=True)
        except (subprocess.SubprocessError, OSError) as exc:
            out.append({"repo": repo, "error": type(exc).__name__})
            print(f"{repo:45} error {type(exc).__name__}", flush=True)
    (ROOT / "bench" / "sweep.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "bench" / "targets.txt")
