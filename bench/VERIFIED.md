# Findings verified by reading the code

From the read-only scan of 30 public repositories (`bench/sweep.json`, scanned 27 October 2026).
Every row below was read by hand at the commit shown. None is listed in Arthi Arumugam's merged or
open pull requests as of 9 October 2026. Nothing here has been reported upstream. Each one needs a
small reproduction before it is filed.

| # | Repository @ commit | Where | Class | What goes wrong |
|---|---|---|---|---|
| 1 | confident-ai/deepeval @ 5410e382 | `deepeval/anthropic/extractors.py:69` | 1, cache tokens | The Anthropic integration records `usage.input_tokens` as the span's input token count. Anthropic's `input_tokens` excludes cache reads and cache writes, so a cached call is logged with a fraction of its real input. |
| 2 | truera/trulens @ 534c93a0 | `src/providers/anthropic/trulens/providers/anthropic/endpoint.py:87-103` | 1, cache tokens | Token count and cost use `input_tokens + output_tokens` only. Cache reads and writes are neither counted nor priced, so cost is under-reported on every cached call. |
| 3 | truera/trulens @ 534c93a0 | `src/core/trulens/core/otel/client_hooks/tracing.py:363-374` | 1, cache tokens | Agent spans built from Claude Code and Cursor hook events total `input_tokens + output_tokens`. Coding-agent sessions are served mostly from cache, so the recorded total misses most of the input. |
| 4 | traceloop/openllmetry @ 8d9c93f3 | `packages/opentelemetry-instrumentation-bedrock/.../span_utils.py:472` | 1, cache tokens | For Anthropic models through Bedrock `invoke_model`, prompt tokens are `usage.input_tokens`; the cache fields are not read. The Converse path in the same file (line 1078) does read them. |
| 5 | explodinggradients/ragas @ 298b6827 | `src/ragas/cost.py:78-106` | 1, cache tokens | `get_token_usage_for_anthropic` reads `usage.input_tokens` only, so evaluation cost for Anthropic judges leaves out cached input. |
| 6 | BerriAI/litellm @ cfe0100e | `litellm/proxy/common_request_processing.py:2353` | 2, a guard drops a legal 0 | `if user_temperature:` skips the CLI value when it is 0, so `litellm --temperature 0` has no effect. |
| 7 | agno-agi/agno @ 3378e643 | `libs/agno/agno/models/azure/claude.py:132` | 2, a guard drops a legal 0 | `if self.temperature:` never sends `temperature=0`, so Anthropic's default of 1.0 applies. The parent class in `models/anthropic/claude.py:561` uses `is not None`. |
| 8 | confident-ai/deepeval @ 5410e382 | `deepeval/metrics/turn_contextual_relevancy/turn_contextual_relevancy.py:588` | 3, silent number | With no turns scored, the metric returns 1, a perfect score, for a conversation where nothing was measured. |
| 9 | comet-ml/opik @ 76a0394e | `sdks/python/src/opik/evaluation/metrics/conversation/llm_judges/user_frustration/metric.py:270` | 3, silent number | With no verdicts, the metric returns 0.0, which reads as "the user was not frustrated at all". |
| 10 | confident-ai/deepeval @ 5410e382 | `deepeval/metrics/goal_accuracy/goal_accuracy.py:288-292` | 3, silent number | With no goal scores, the goal average is 0 and is still averaged in, so the reported score is half the plan score. Reachability not yet reproduced. |
| 11 | BerriAI/litellm @ cfe0100e | `litellm/harness/handlers/tool_loop_handler.py:141-144` | 10, cost dropped | When `completion_cost` raises (for example an unpriced model), the tool loop records 0.0 with no log, so the run reads as free. |

Lower impact or debatable, kept for completeness:

- NVIDIA-NeMo/Evaluator @ ea35ba36, `src/nemo_evaluator/engine/comparison.py:216`: `relative_pct` is 0 when the baseline is 0, even when the candidate moved. `delta` is reported beside it.
- openai/evals @ 8eac7a7d, `evals/solvers/providers/anthropic/anthropic_solver.py:139-141`: same cache exclusion as row 1, in a repository that is no longer actively maintained.
