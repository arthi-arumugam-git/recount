#!/usr/bin/env python3
"""Find token accounting that silently undercounts Anthropic's prompt cache.

Anthropic reports `input_tokens` NET of the prompt cache and bills
`cache_read_input_tokens` and `cache_creation_input_tokens` separately on top. It does not
send a total. So code that computes one as input + output charges its users for a number
smaller than the one the provider billed, and nothing raises.

That defect has been found by hand in five independent agent frameworks: Pipecat, LiveKit
Agents, LlamaIndex, Haystack and mcp-use.

HOW MUCH OF THAT IT ACTUALLY CATCHES

Four of the five, measured rather than asserted. Each framework's source was pulled at the
parent of its fix commit and scanned, and the fixed version was scanned too:

    caught   Pipecat, LiveKit Agents, Haystack, mcp-use
    missed   LlamaIndex

LlamaIndex's defect is in provider-agnostic core code that names no provider, and the gate
below requires one. It is the price of not reporting every OpenAI file in a repository.

The first version of this checker found two of the five. It missed Pipecat, the defect it
is named after, because rules 1 and 2 switch themselves off for any file that mentions the
cache, and Pipecat's file mentioned it four lines above the wrong total. It also reported
LiveKit's merged fix as a defect, because Bedrock spells cache creation "write".

    python cachecheck.py path/to/repo
    python cachecheck.py . --json
    python cachecheck.py . --quiet     # exit code only, for CI

Exit code is 1 when anything is found, so it works as a CI gate.

WHAT IT DELIBERATELY DOES NOT FLAG

OpenAI reports `cached_tokens` INSIDE `prompt_tokens`. Adding it there would double count.
A file that only handles OpenAI-shaped usage is correct as written, and flagging it would be
the same class of error in the opposite direction.

Comments, docstrings and type declarations name these fields without computing anything. An
earlier version flagged `inputTokens?: number;` and a docstring showing sample output, which
is the kind of noise that gets a checker switched off. Rule 2 requires evidence of
arithmetic, not a mention.
"""

import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SUFFIXES = (".py", ".ts", ".tsx", ".js", ".mjs", ".jsx", ".go", ".rb", ".java", ".kt")
SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "dist", "build", "__pycache__",
    ".next", ".turbo", "vendor", "target", ".mypy_cache", ".pytest_cache",
}

CACHE_READ = re.compile(r"cache_read_input_tokens|cacheReadInputTokens", re.I)
# Bedrock spells cache creation "write". Without its aliases rule 3 fired on code that
# handles both counters correctly, including the merged fixes in LiveKit's and Haystack's
# Bedrock paths. A checker that flags the fix is worse than one that stays quiet.
CACHE_WRITE = re.compile(
    r"cache_creation_input_tokens|cacheCreationInputTokens|"
    r"cache_write_input_tokens|cacheWriteInputTokens", re.I
)

# An accessor chain in front of the second term: `usage.`, `resp.usage.`, `u["usage"].`.
# Without this the patterns below only matched a bare `input_tokens + output_tokens`, and
# real code almost always writes `usage.input_tokens + usage.output_tokens`. Those files
# were still reported by rule 2, but through the weaker evidence path, so the rule named
# after the defect was silently missing the defect's most common spelling. Found by the
# tests in this package, which is the whole argument for having them.
_ACC = r"(?:[A-Za-z_]\w*\s*(?:\.\s*|\[\s*[\x27\"]?\w+[\x27\"]?\s*\]\s*))*"


def _sum(first, second):
    return re.compile(first + r"\s*\+\s*" + _ACC + second)


SUMS = [
    _sum("input_tokens", "output_tokens"),
    _sum("output_tokens", "input_tokens"),
    _sum("prompt_tokens", "completion_tokens"),
    _sum("completion_tokens", "prompt_tokens"),
    _sum("inputTokens", "outputTokens"),
    _sum("outputTokens", "inputTokens"),
    _sum("promptTokens", "completionTokens"),
]

ANTHROPIC = re.compile(r"anthropic|claude-[0-9a-z]|bedrock|input_tokens|inputTokens", re.I)

# The gate above accepts a bare `input_tokens`, which any provider may use for its own
# gross figure. That is wanted for the rules that only need a plausible total, and wrong
# for the rule that reads one field name being assigned to another, where the whole
# finding rests on the two names meaning different things on Anthropic specifically.
ANTHROPIC_NAMED = re.compile(r"anthropic|claude|bedrock", re.I)

# A name whose contract INCLUDES the cached tokens, being fed from one that excludes them.
NET_TO_GROSS = re.compile(
    r"(?:prompt_tokens|promptTokens)[\x27\"]?\s*\]?\s*=\s*(?!=)([^\n;]{0,200})"
)
NET_FIELD = re.compile(r"input_tokens|inputTokens")
# `input_tokens.get("speechTokens")` is a local bag of counts that happens to carry the
# name, not the provider's scalar. Pipecat's Nova Sonic service reads exactly that, and
# the field it builds is speech and text tokens, which no prompt cache ever serves.
NET_AS_CONTAINER = re.compile(r"(?:input_tokens|inputTokens)\s*(?:\.\s*get\s*\(|\[)")

TOTAL_LHS = re.compile(
    r"\b(?:total_tokens|totalTokens|total_token_count|totalTokenCount)\s*[=:]\s*(?!=)"
)
OUTPUT_FIELD = re.compile(r"output_tokens|outputTokens|completion_tokens|completionTokens", re.I)
# Not READS_INPUT, which knows only Anthropic's own spelling. The wrong total is usually
# written in the local vocabulary, and Pipecat's said `prompt_tokens + completion_tokens`.
INPUT_FIELD = re.compile(r"input_tokens|inputTokens|prompt_tokens|promptTokens", re.I)


def expression_after(text, start, limit=800):
    """The right-hand side starting at `start`, to the end of its bracketed expression.

    Bracket depth is what makes this work on real code. A correct total is usually written
    across several lines inside parentheses, so stopping at the first newline would read
    only its first term and call the fix a defect.
    """
    depth, out = 0, []
    for ch in text[start:start + limit]:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and (ch in ",;" or ch == "\n"):
            break
        out.append(ch)
    return "".join(out)


# Any identifier carrying the word, not just the provider's exact field name. Code that
# folds the cache in almost always parks it in a local first (`cached`, `cache_read_tokens`),
# so matching only the wire field name reads the corrected line as a defect.
CACHEISH = re.compile(r"cache", re.I)
IDENT = re.compile(r"[A-Za-z_]\w*")


def folds_cache_in(code, name):
    """True when `name` is anywhere assigned an expression that accounts for the cache.

    A total of input plus output is correct whenever the input term was already made
    gross further up. LiveKit's Bedrock plugin does exactly that: it adds the two cache
    counters into `prompt_tokens` on one line and totals it on another. Reading only the
    total's own expression calls that fix a bug.
    """
    for m in re.finditer(r"\b" + re.escape(name) + r"\s*(?:[-+*]?=)\s*(?!=)", code):
        if CACHEISH.search(expression_after(code, m.end())):
            return True
    return False


def near(text, offset, radius=8):
    """The lines within `radius` of `offset`. The cache term is often added a line or two
    from the assignment it corrects rather than inside it, so an expression-only test
    reports those corrected files as defects."""
    lines = text.split("\n")
    i = text[:offset].count("\n")
    return "\n".join(lines[max(0, i - radius):i + radius + 1])
OPENAI_SHAPED = re.compile(
    r"prompt_tokens_details|promptTokensDetails|input_tokens_details|cached_tokens", re.I
)
READS_INPUT = re.compile(r"input_tokens|inputTokens")

# Evidence the file does something with the number rather than merely naming it.
USES_ARITHMETICALLY = re.compile(
    r"(input_tokens|inputTokens|prompt_tokens|promptTokens)\s*[-+*/]"
    r"|[-+*/]\s*(input_tokens|inputTokens|prompt_tokens|promptTokens)"
    r"|(total|sum|cost|price|billed|usage)\w*\s*[:=][^\n;]*"
    r"(input_tokens|inputTokens|prompt_tokens|promptTokens)",
    re.I,
)

BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT = re.compile(r"^[ \t]*(//|#).*$", re.M)
PY_DOCSTRING = re.compile(r'("{3}|\x27{3}).*?\1', re.S)


def strip_noise(text, path):
    """Remove comments and docstrings. They name fields without computing anything."""
    # Keep the newlines of what is removed, so reported line numbers still match the file.
    # (Recount change to the vendored copy: blanking a multi-line docstring to one space
    # shifted every later finding up by the docstring's height.)
    keep_lines = lambda m: " " + "\n" * m.group(0).count("\n")  # noqa: E731
    text = BLOCK_COMMENT.sub(keep_lines, text)
    text = LINE_COMMENT.sub(" ", text)
    if path.endswith(".py"):
        text = PY_DOCSTRING.sub(keep_lines, text)
    return text


def is_openai_shaped(text):
    """True when the cache handling is OpenAI's, where the cache is already inside."""
    return bool(OPENAI_SHAPED.search(text)) and not CACHE_READ.search(text)


# Test fixtures construct usage objects; they do not bill anyone. Both false positives in
# the first validated run were a conftest and a .test.ts. Skipped by default, --tests to keep.
TEST_PATH = re.compile(r"(^|[\/])(tests?|__tests__|spec|fixtures)([\/]|$)|"
                       r"(^|[\/])(test_[^\/]*|conftest)\.py$|"
                       r"\.(test|spec)\.[jt]sx?$", re.I)


def walk(root):
    if os.path.isfile(root):
        yield root
        return
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            if name.endswith(SUFFIXES):
                yield os.path.join(base, name)


def check_file(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return []
    if not ANTHROPIC.search(raw):
        return []

    code = strip_noise(raw, path)
    if not READS_INPUT.search(code):
        return []

    findings = []
    lines = raw.split("\n")
    has_read = bool(CACHE_READ.search(code))
    has_write = bool(CACHE_WRITE.search(code))
    openai_only = is_openai_shaped(code)

    # Every rule below asks a question that only has an answer on Anthropic and Bedrock,
    # where the input count is net of the cache. Elsewhere the same field names mean
    # something else and the same code is correct.
    #
    # Without this the checker fired on Pipecat's OpenAI, Google and SambaNova services,
    # because Pipecat names its own breakdown field `cache_read_input_tokens` and every
    # service that fills it therefore looked Anthropic-shaped. Six of eleven findings on
    # that repository were this, and all six were wrong. It also fired on Haystack's
    # Cohere generator, whose `billed_units.input_tokens` is already gross.
    #
    # The cost is real and is stated in the README: provider-agnostic code that aggregates
    # usage without naming anyone is no longer read. LlamaIndex's core token counter is
    # exactly that shape, and this checker does not find it.
    named = bool(ANTHROPIC_NAMED.search(raw))
    if not named:
        return []

    def line_of(offset_text, match):
        return offset_text[:match.start()].count("\n") + 1

    # 1. A total that cannot include the cache, in a file that knows about Anthropic.
    if not has_read and not openai_only:
        for i, line in enumerate(lines, 1):
            if LINE_COMMENT.match(line):
                continue
            for rx in SUMS:
                if rx.search(line):
                    findings.append({
                        "rule": "cache-blind-total",
                        "path": path, "line": i, "evidence": line.strip()[:120],
                        "why": "totals input plus output, and this file never reads "
                               "cache_read_input_tokens. On Anthropic those tokens are "
                               "billed and are not inside input_tokens.",
                    })
                    break

    # 2. Computes with Anthropic usage and never reads the cache counter at all.
    if not has_read and not openai_only:
        m = USES_ARITHMETICALLY.search(code)
        if m:
            findings.append({
                "rule": "cache-read-never-read",
                "path": path, "line": line_of(code, m),
                "evidence": m.group(0).strip()[:120],
                "why": "computes with input_tokens and never reads "
                       "cache_read_input_tokens, so every token served from cache is "
                       "invisible to this accounting.",
            })

    # 4. A total that leaves the cache out, in a file that reads the cache elsewhere.
    #
    # This is the shape the tool was named after and the one it used to miss entirely.
    # Rules 1 and 2 both switch off the moment a file mentions the cache, on the theory
    # that such a file has understood the problem. Pipecat disproves it: both its Anthropic
    # and Bedrock services tracked cache reads and cache writes in the breakdown they
    # reported, and still wrote `total_tokens=prompt_tokens + completion_tokens`. The
    # counters are right there in the same function. Only the total is wrong.
    #
    # So this reads the total's own expression rather than the file. A file knowing the
    # word is not evidence that this sum used it.
    if has_read:
        for m in TOTAL_LHS.finditer(code):
            expr = expression_after(code, m.end())
            if not expr.strip():
                continue
            if CACHEISH.search(expr):
                continue
            inputs = [w for w in IDENT.findall(expr) if INPUT_FIELD.fullmatch(w)]
            if any(folds_cache_in(code, w) for w in inputs):
                continue
            if INPUT_FIELD.search(expr) and OUTPUT_FIELD.search(expr):
                findings.append({
                    "rule": "total-excludes-cache",
                    "path": path, "line": line_of(code, m),
                    "evidence": " ".join(expr.split())[:120],
                    "why": "totals input plus output while this file reads the cache "
                           "counters elsewhere. The breakdown is right and the total is "
                           "not, which is harder to spot than ignoring the cache outright.",
                })

    # 5. A net input figure assigned to a name that is supposed to be gross.
    #
    # `prompt_tokens` is OpenAI's name and includes the cached tokens. `input_tokens` is
    # Anthropic's and excludes them. Copying one into the other keeps the name's promise
    # and drops the tokens, with no arithmetic anywhere for the earlier rules to catch.
    # Haystack shipped `usage["prompt_tokens"] = usage.pop("input_tokens")` for exactly
    # this reason.
    for m in NET_TO_GROSS.finditer(code):
        rhs = m.group(1)
        if not NET_FIELD.search(rhs) or CACHEISH.search(rhs):
            continue
        if NET_AS_CONTAINER.search(rhs):
            continue
        if CACHEISH.search(near(code, m.start())):
            continue
        findings.append({
            "rule": "net-input-as-gross",
            "path": path, "line": line_of(code, m),
            "evidence": " ".join(m.group(0).split())[:120],
            "why": "assigns input_tokens to prompt_tokens. Those names do not mean "
                   "the same thing: prompt_tokens includes the cached tokens and "
                   "input_tokens is net of them, so the cache is lost in the rename.",
        })

    # 3. Handles cache reads but not cache writes, which Anthropic bills above base rate.
    if has_read and not has_write:
        m = CACHE_READ.search(code)
        findings.append({
            "rule": "cache-creation-ignored",
            "path": path, "line": line_of(code, m),
            "evidence": m.group(0)[:120],
            "why": "reads cache_read_input_tokens but never "
                   "cache_creation_input_tokens. Cache writes are billed above the "
                   "base rate, so they cost more per token than the ones remembered.",
        })
    return findings


def main():
    ap = argparse.ArgumentParser(description="Find token accounting blind to Anthropic's prompt cache.")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--tests", action="store_true",
                    help="also scan test files, which normally only build fixtures")
    args = ap.parse_args()

    findings, scanned = [], 0
    for path in walk(args.root):
        # Normalise the separator first. The pattern is written with forward slashes and
        # os.path.join produces backslashes on Windows, so tests/conftest.py was being
        # scanned there and skipped everywhere else. Same rule, either platform.
        if not args.tests and TEST_PATH.search(path.replace(chr(92), "/")):
            continue
        scanned += 1
        findings += check_file(path)

    if args.as_json:
        print(json.dumps({"scanned": scanned, "findings": findings}, indent=2))
        return 1 if findings else 0
    if args.quiet:
        return 1 if findings else 0

    if not findings:
        print(f"Scanned {scanned} files. Nothing found.")
        print("That is a result, not a failure to look: every total in this tree already")
        print("accounts for the prompt cache, or the file is OpenAI-shaped where the cache")
        print("is already inside prompt_tokens.")
        return 0

    by_rule = {}
    for f in findings:
        by_rule.setdefault(f["rule"], []).append(f)

    print(f"Scanned {scanned} files. {len(findings)} findings.\n")
    for rule, group in by_rule.items():
        print("=" * 78)
        print(f"{rule}  ({len(group)})")
        print("=" * 78)
        print(f"  {group[0]['why']}\n")
        for f in group:
            try:
                rel = os.path.relpath(f["path"], args.root)
            except ValueError:
                rel = f["path"]
            print(f"  {rel}:{f['line']}")
            print(f"      {f['evidence']}")
        print()
    print("Every rule here comes from a defect found by hand in a shipped library, each")
    print("with a pull request and a test that fails on main:")
    print("  https://github.com/arthi-arumugam-git/wrong-numbers")
    return 1


if __name__ == "__main__":
    sys.exit(main())
