import textwrap
from pathlib import Path

import pytest

from recount.scan import scan


def run(tmp_path: Path, code: str, name: str = "metrics.py"):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(code))
    return scan(tmp_path)


def rules(findings):
    return sorted(f.rule for f in findings)


# ---- class 3: silent zero -------------------------------------------------

@pytest.mark.parametrize("code", [
    "def rate(c, r):\n    return c / r if r > 0 else 0.0\n",
    "def avg_metric(v):\n    return sum(v) / len(v) if v else 0.0\n",
    "def pct_metric(v):\n    return (sum(v) / len(v) * 100.0) if v else 0.0\n",
    "def mean_metric(v):\n    return 0.0 if not v else sum(v) / len(v)\n",
])
def test_guarded_division_is_flagged(tmp_path, code):
    assert "guarded-division-returns-number" in rules(run(tmp_path, code))


def test_empty_return_with_else_is_flagged(tmp_path):
    code = """
    def score_metric(values):
        if len(values) == 0:
            return 0.0
        else:
            return sum(values) / len(values)
    """
    assert "empty-input-returns-number" in rules(run(tmp_path, code))


def test_nan_fallback_is_not_flagged(tmp_path):
    code = """
    def score_metric(values):
        if not values:
            return float("nan")
        return sum(values) / len(values)
    def rate_metric(c, r):
        return c / r if r > 0 else float("nan")
    """
    assert run(tmp_path, code) == []


def test_non_metric_code_is_left_alone(tmp_path):
    code = "def resize(w, h):\n    return w / h if h else 0.0\n"
    assert run(tmp_path, code, name="image.py") == []


def test_divisor_fallback(tmp_path):
    code = "def tool_score(xs):\n    d = len(xs) if len(xs) > 0 else 1\n    return sum(xs) / d\n"
    assert "divisor-fallback-to-one" in rules(run(tmp_path, code))


# ---- class 2: guard drops a legal 0 --------------------------------------

def test_truthiness_guard(tmp_path):
    code = """
    class D:
        def load(self, r):
            if r.temperature:
                self.temperature = r.temperature
    """
    assert rules(run(tmp_path, code, "driver.py")) == ["truthiness-guard-drops-zero"]


def test_is_not_none_guard_is_fine(tmp_path):
    code = """
    class D:
        def load(self, r):
            if r.temperature is not None:
                self.temperature = r.temperature
    """
    assert run(tmp_path, code, "driver.py") == []


def test_or_default(tmp_path):
    code = "def f(kw):\n    return kw.get('temperature') or 0.7\n"
    assert rules(run(tmp_path, code, "client.py")) == ["or-default-replaces-zero"]


def test_or_zero_default_is_fine(tmp_path):
    code = "def f(kw):\n    return kw.get('cost') or 0\n"
    assert run(tmp_path, code, "client.py") == []


def test_isinstance_float_only(tmp_path):
    code = "def f(u):\n    if isinstance(u.cost, float):\n        return u.cost\n"
    assert rules(run(tmp_path, code, "client.py")) == ["isinstance-float-drops-int"]
    ok = "def f(u):\n    if isinstance(u.cost, (int, float)):\n        return u.cost\n"
    assert run(tmp_path / "ok", ok, "client.py") == []


# ---- class 11: setting accepted and ignored -------------------------------

def test_ignored_timeout(tmp_path):
    code = """
    class Client:
        def __init__(self, api_key, base_path="x", timeout=30):
            self.api_key = api_key
            self.client = make(base_path)
    """
    assert rules(run(tmp_path, code, "client.py")) == ["parameter-accepted-and-ignored"]


def test_used_or_abstract_parameters_are_fine(tmp_path):
    code = """
    from abc import abstractmethod
    class Client:
        def __init__(self, timeout=30):
            self.timeout = timeout
        @abstractmethod
        def call(self, timeout=None):
            ...
        def stub(self, temperature=0.0):
            raise NotImplementedError
    """
    assert run(tmp_path, code, "client.py") == []


# ---- class 10: cost silently dropped ---------------------------------------

def test_zero_price_default(tmp_path):
    code = "def price(model):\n    return PRICES.get(model, 0)\n"
    assert rules(run(tmp_path, code, "billing.py")) == ["unknown-model-priced-at-zero"]


def test_price_field_default_is_fine(tmp_path):
    code = "def price(pricing):\n    return pricing.get('input_cost_per_token', 0.0)\n"
    assert run(tmp_path, code, "billing.py") == []


def test_interface_method_params_are_fine(tmp_path):
    code = """
    class Env:
        def step(self, action, timeout=30):
            return self.inner.step(action)
    """
    assert run(tmp_path, code, "env.py") == []


def test_swallowed_cost_error(tmp_path):
    code = """
    def attrs(r):
        out = {}
        try:
            out["cost"] = calc_price(r)
        except Exception:
            pass
        return out
    """
    assert rules(run(tmp_path, code, "usage.py")) == ["cost-error-swallowed"]


def test_logged_cost_error_is_fine(tmp_path):
    code = """
    def attrs(r):
        try:
            return calc_price(r)
        except Exception:
            logger.warning("no price for %s", r)
            return None
    """
    assert run(tmp_path, code, "usage.py") == []


# ---- class 1: cache tokens (vendored cachecheck) ---------------------------

def test_cache_blind_total(tmp_path):
    code = """
    import anthropic
    def usage(u):
        prompt_tokens = u.input_tokens
        total = u.input_tokens + u.output_tokens
        return prompt_tokens, total
    """
    assert any(f.bug_class == 1 for f in run(tmp_path, code, "anthropic_llm.py"))


def test_f_score_limit_is_fine(tmp_path):
    code = """
    def f1_metric(p, r, xs):
        if p + r == 0:
            return 0.0
        return 2 * p * r / (p + r) + sum(xs) / len(xs)
    """
    assert "empty-input-returns-number" not in rules(run(tmp_path, code))


def test_float_then_int_branch_is_fine(tmp_path):
    code = "def f(u):\n    if isinstance(u.cost, float):\n        return u.cost\n    if isinstance(u.cost, int):\n        return float(u.cost)\n"
    assert run(tmp_path, code, "client.py") == []


def test_generate_is_not_a_rate(tmp_path):
    code = "def g(x):\n    try:\n        return generate(x)\n    except Exception:\n        pass\n"
    assert run(tmp_path, code, "usage.py") == []


# ---- scanning hygiene --------------------------------------------------------

def test_tests_and_venvs_are_skipped(tmp_path):
    bad = "def avg_metric(v):\n    return sum(v) / len(v) if v else 0.0\n"
    run(tmp_path, bad, "tests/test_metrics.py")
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "metrics.py").write_text(bad)
    assert scan(tmp_path) == []


def test_examples_and_scripts_are_skipped_unless_asked(tmp_path):
    bad = "def avg_metric(v):\n    return sum(v) / len(v) if v else 0.0\n"
    run(tmp_path, bad, "examples/metrics.py")
    run(tmp_path, bad, "scripts/metrics.py")
    assert scan(tmp_path) == []
    assert len(scan(tmp_path, everything=True)) == 2


def test_unparseable_file_is_skipped(tmp_path):
    assert run(tmp_path, "def broken(:\n", "metrics.py") == []


def test_cache_finding_line_survives_docstrings(tmp_path):
    code = '''
    """Module docstring
    over three lines.
    """
    import anthropic


    def usage(u):
        """Another
        docstring."""
        total = u.input_tokens + u.output_tokens
        return total
    '''
    found = [f for f in run(tmp_path, code, "anthropic_llm.py") if f.bug_class == 1]
    assert found
    lines = textwrap.dedent(code).splitlines()
    for f in found:
        assert "input_tokens" in lines[f.line - 1], (f.line, f.snippet)
