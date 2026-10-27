# Precision on a random sample

The scan of 30 repositories at their default branch produced 590 findings in shipped code (tests, examples, scripts, docs and notebooks skipped). Forty were drawn at random (`random.seed(2027)`, `bench/sample3.json`) and each was read by hand. Labels are in `bench/precision_sample.json`.

| Label | Count | Meaning |
|---|---|---|
| real | 3 | A reachable case where a reported number is wrong. |
| debatable | 7 | The number is arguably wrong; a maintainer could reasonably keep it. |
| benign | 15 | The code has the shape, but the number is right by convention or never reported. |
| false alarm | 14 | The rule misread the code. |
| unclear | 1 | Not resolved by reading. |

By rule:

| Rule | real | debatable | benign | false alarm | unclear |
|---|---|---|---|---|---|
| guarded-division-returns-number | 0 | 3 | 7 | 0 | 0 |
| truthiness-guard-drops-zero | 1 | 0 | 4 | 2 | 0 |
| isinstance-float-drops-int | 0 | 0 | 0 | 6 | 0 |
| empty-input-returns-number | 1 | 1 | 3 | 0 | 0 |
| cache-read-never-read | 0 | 0 | 0 | 4 | 0 |
| parameter-accepted-and-ignored | 0 | 2 | 0 | 0 | 0 |
| max-one-denominator | 0 | 0 | 0 | 1 | 0 |
| cost-error-swallowed | 1 | 0 | 0 | 0 | 0 |
| total-excludes-cache | 0 | 0 | 0 | 1 | 0 |
| or-default-replaces-zero | 0 | 0 | 1 | 0 | 0 |
| unknown-model-priced-at-zero | 0 | 1 | 0 | 0 | 0 |
| net-input-as-gross | 0 | 0 | 0 | 0 | 1 |

What this says: the rules find the shape reliably (11 of 12 known fixes, `bench/replay.json`) but most matches in code they were not written against are harmless. Static matching alone is a candidate list. Deciding which candidates are real takes reading the surrounding code, which is the step that needs to be automated next.

Two earlier samples (seeds 20261027 and 1101) were used to fix false-alarm patterns before this one was drawn: price words matching inside other words, F-score limits, float checks followed by an int branch, example and script folders, and a line-number shift in the vendored cache rules after multi-line docstrings.
