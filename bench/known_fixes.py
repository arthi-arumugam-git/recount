"""Arthi's merged fixes (resume appendix, as of 9 October 2026), with the bug class each fixes.

class: the wrong-numbers taxonomy id (1-13), or None where the fix is outside it.
Recovering 'before' and 'after' needs no API: refs/pull/<n>/head is the fix, and
its merge-base with the default branch is the code the fix was written against.
"""

KNOWN = [
    ("pipecat-ai/pipecat", 5163, 1, "Count cached input tokens in total_tokens for Anthropic and Bedrock"),
    ("UKGovernmentBEIS/inspect_evals", 2042, 6, "Stop penalising optional parameters at their schema default"),
    ("UKGovernmentBEIS/inspect_evals", 2036, 3, "Restore the denominator on confidence and apologize_rate"),
    ("livekit/agents", 6663, 1, "Count cached tokens in Bedrock's prompt_tokens"),
    ("roboflow/supervision", 2468, 5, "Track prediction-only classes in Recall"),
    ("deepset-ai/haystack-core-integrations", 3717, 1, "Include cached tokens in the OpenAI-compatible prompt_tokens"),
    ("pydantic/genai-prices", 520, 10, "Add AWS Bedrock prices for Writer Palmyra X4 and X5"),
    ("UKGovernmentBEIS/inspect_evals", 2097, 7, "Stop scoring truncated reasoning as the model's answer"),
    ("roboflow/inference", 2745, 13, "Stop usage tracking failures from failing the inference call"),
    ("mcp-use/mcp-use", 2127, 1, "Count Anthropic cache tokens and stop message_delta erasing usage"),
    ("UKGovernmentBEIS/inspect_evals", 2123, 3, "Stop reporting a stereotype score built from samples never scored"),
    ("ogx-ai/ogx", 6415, 12, "Stop counting cached tokens twice in the Anthropic-compat usage"),
    ("UKGovernmentBEIS/inspect_evals", 2174, 3, "Return nan rather than 0.0 when a metric has no samples"),
    ("respanai/respan", 351, None, "Add control cases for the thinking-token fold (tests only)"),
    ("UKGovernmentBEIS/inspect_evals", 2173, None, "Document what a metric reports when its denominator is empty (docs only)"),
    ("UKGovernmentBEIS/inspect_evals", 2179, 3, "Report nan rather than 0.0 when percentage_of has no samples"),
    ("UKGovernmentBEIS/inspect_evals", 2230, 3, "Mean_of reports nan rather than 0.0 when nothing was averaged"),
    ("dbt-labs/metricflow", 2114, None, "Keep non-deterministic expressions materialized in the sub-query reducer"),
    ("mistralai/mistral-common", 289, None, "Keep at least one pixel per axis when resizing an image"),
    ("truera/trulens", 2726, None, "Stop reading a judge's stated scale as its rating"),
    ("pydantic/logfire", 2162, 10, "Price Bedrock calls under the aws provider"),
    ("truera/trulens", 2737, None, "Score ground-truth rows in row order, not index-label order"),
    ("truera/trulens", 2738, 3, "Report nan, not 0.0, when an IR metric is undefined"),
    ("EleutherAI/lm-evaluation-harness", 4068, None, "Report a sample count that does not depend on metric order"),
    ("truera/trulens", 2748, None, "Refuse a score list that does not match the labels"),
    ("unslothai/unsloth", 8906, 11, "Pass force_download through to snapshot_download"),
]
