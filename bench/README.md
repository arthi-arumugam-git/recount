# Benchmarks

Everything here is read only. Repositories are cloned into a temporary folder and scanned; nothing is pushed, opened or reported.

- `known_fixes.py`: the 26 fixes merged upstream by Arthi Arumugam as of 9 October 2026, with the taxonomy class of each.
- `fetch.py`: clones each repository, recovers the code before and after the fix from git alone, and writes `fixes.json`. One edit was made by hand afterwards: respanai/respan#351 changes tests only, so its file list is empty.
- `replay.py`: scans the before and after code of each fix and writes `replay.json`.
- `targets.txt`, `sweep.py`: the 30 repositories scanned at their default branch, and the scan itself; output in `sweep.json`.
- `sample3.json`, `precision_sample.json`, `PRECISION.md`: the random sample of 40 findings, its hand labels, and the summary.
- `sample2.json`: an earlier sample, used to fix false-alarm patterns before `sample3` was drawn.
- `VERIFIED.md`: findings read and confirmed by hand. None has been reported upstream.

```
python bench/fetch.py      # needs network access to github.com
python bench/replay.py
python bench/sweep.py
```
