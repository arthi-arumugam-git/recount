# Recount

Recount reads a Python codebase and points at the places where an evaluation score, a token count or a cost can come out wrong while nothing raises an error.

It reads source only. Nothing in the scanned code is imported or run.

```
pip install .
recount path/to/repo                 # list findings; exit code 1 if any, for CI
recount path/to/repo --json          # machine-readable
recount path/to/repo --tests         # also scan test files
recount path/to/repo --everything    # also scan examples, scripts, docs and notebooks
```

## What it looks for

The rules come from a taxonomy of real bugs, each one fixed in a public project: [wrong-numbers](https://github.com/arthi-arumugam-git/wrong-numbers). Five of its thirteen classes are covered so far.

1. **Cache tokens left out.** Anthropic and Bedrock report `input_tokens` net of cached tokens. Code that treats it as the whole prompt under-counts tokens and cost on every cached call. These rules are [cachecheck](https://github.com/arthi-arumugam-git/cachecheck) (MIT), vendored in `recount/_vendor`.
2. **A guard drops a legal 0.** `if temperature:` is false for `temperature=0`, so the setting is silently skipped.
3. **A silent number when nothing was measured.** `sum(xs) / len(xs) if xs else 0.0` reports 0.0, a real-looking score, for an empty run.
10. **Cost silently dropped.** A price lookup that fails becomes 0 or nothing, and the call reads as free.
11. **A setting accepted and ignored.** A constructor takes `timeout=` and never uses it.

## How well it works

Two tests, both reproducible from `bench/`.

**Rediscovery.** For 26 fixes merged upstream by the taxonomy's author, Recount was run on the code as it was before each fix. It flags the bug in 11 of the 12 fixes that fall in the five covered classes (`bench/replay.py`, `bench/replay.json`). The script also reports a hit on the fixed lines of ogx-ai/ogx#6415, a class-12 fix, but the flagged problem there is a different one (cache writes not recorded), so it is not counted. The rules were written from these same bugs, so this shows the rules match what they were built from, not how they do on new code.

**New code.** Recount scanned 30 widely used evaluation, agent and tracing libraries at their default branch on 27 October 2026 (`bench/sweep.py`, `bench/sweep.json`): 590 findings in shipped code. A random sample of 40 was read by hand: 3 real, 7 debatable, 15 benign, 14 false alarms, 1 unclear (`bench/PRECISION.md`). Separately, 11 findings were read and confirmed as real bugs that have not been reported (`bench/VERIFIED.md`).

So the rules are a candidate list, not a verdict. Most of what they match in unfamiliar code is harmless. The next step is a verifier that reads the surrounding code and decides, with a reproduction, which candidates are real.

## Tests

```
pip install ".[test]"
pytest
```

## License

MIT. The vendored cachecheck rules are MIT, by the same author; see `recount/_vendor/CACHECHECK_LICENSE`. One change was made to them: removed docstrings and block comments now keep their line breaks, so reported line numbers match the file.
