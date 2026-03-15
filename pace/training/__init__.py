"""PACE Training Data Pipeline — public exports.

Collects, scores, and exports PACE-generated story traces for LLM fine-tuning.

Usage (from a script or the DataExportHook):

    from training.collector import collect_story_trace, collect_all_traces
    from training.exporter import export_sft_jsonl, export_reward_jsonl

    traces = collect_all_traces(pace_dir=Path(".pace"), min_gate_pass_rate=0.8)
    export_sft_jsonl(traces, Path("sft_corpus.jsonl"))
    export_reward_jsonl(traces, Path("reward_corpus.jsonl"))
"""

from training.collector import StoryTrace, collect_all_traces, collect_story_trace
from training.exporter import export_reward_jsonl, export_sft_jsonl

__all__ = [
    "StoryTrace",
    "collect_story_trace",
    "collect_all_traces",
    "export_sft_jsonl",
    "export_reward_jsonl",
]
