"""Recover the before/after commits of each known fix using git only.

For each (repo, pr): treeless clone of the default branch, fetch refs/pull/<pr>/head,
before = merge-base(pr head, default branch), after = pr head.
Writes bench/fixes.json with the changed Python files. Read only; nothing is pushed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from known_fixes import KNOWN  # noqa: E402

ROOT = Path(__file__).resolve().parent
REPOS = Path(os.environ.get("AUDIT_REPOS", "/tmp/audit-repos"))
ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


def git(*args, cwd=None, timeout=600):
    return subprocess.run(["git", *args], cwd=cwd, env=ENV, check=True, capture_output=True,
                          text=True, timeout=timeout).stdout.strip()


def ensure_clone(repo: str) -> Path:
    dest = REPOS / repo.replace("/", "__")
    if not dest.exists():
        git("clone", "--quiet", "--filter=tree:0", "--no-checkout", f"https://github.com/{repo}.git", str(dest))
    return dest


def main():
    REPOS.mkdir(parents=True, exist_ok=True)
    out = []
    for repo, pr, cls, title in KNOWN:
        entry = {"repo": repo, "pr": pr, "class": cls, "title": title}
        try:
            d = ensure_clone(repo)
            git("fetch", "--quiet", "--filter=tree:0", "origin", f"refs/pull/{pr}/head:refs/remotes/pr/{pr}", cwd=d)
            head = git("rev-parse", f"refs/remotes/pr/{pr}", cwd=d)
            default = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=d)
            base = git("merge-base", head, default, cwd=d)
            if base == head:
                # The branch was merged as-is, so the fix is already in the default
                # branch's history. "Before" is then the default branch just before
                # the merge commit that brought the fix in.
                merges = git("log", "--merges", "--ancestry-path", "--format=%H %P",
                             f"{head}..{default}", cwd=d).splitlines()
                merge = next((m for m in reversed(merges) if head in m.split()[2:]), None)
                base = merge.split()[1] if merge else git("rev-parse", f"{head}^", cwd=d)
                entry["before_from"] = "merge first parent" if merge else "parent of fix head"
            files = git("diff", "--name-only", base, head, cwd=d).splitlines()
            entry.update(before=base, after=head, files=files,
                         py_files=[f for f in files if f.endswith(".py")])
        except subprocess.SubprocessError as exc:
            entry["error"] = f"{type(exc).__name__}: {getattr(exc, 'stderr', '')[:200]}"
        print(repo, pr, entry.get("before", "")[:8], entry.get("after", "")[:8], entry.get("error", ""), flush=True)
        out.append(entry)
    (ROOT / "fixes.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
