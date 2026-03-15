"""PACE DataExportHook — training data collection plugin.

Registered directly by the orchestrator (not via entry points) when
`training.export_on_ship: true` is set in pace.config.yaml.

On every `day_shipped` event the hook:
1. Reads `.pace/day-N/` artifacts via training.collector.collect_story_trace().
2. Skips the trace if gate_pass_rate < min_gate_pass_rate.
3. Appends the trace to the configured JSONL corpus files via training.exporter.

Configuration (from PaceConfig.training):
    output_dir:         Path to the directory where JSONL files are written.
                        Created on first write.  Default: "training_data/".
    format:             "sft" | "reward" | "both".  Default: "both".
    min_gate_pass_rate: Minimum GATE pass rate [0.0–1.0] to include a trace.
                        Default: 0.0 (all shipped stories collected).

Output files:
    <output_dir>/sft_corpus.jsonl      — SFT fine-tuning lines
    <output_dir>/reward_corpus.jsonl   — RLHF reward lines
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plugins.base import HookBase, PluginManifest


class DataExportHook(HookBase):
    """Export shipped story traces to JSONL training corpus on day_shipped."""

    def __init__(self) -> None:
        self._output_dir = Path("training_data")
        self._format = "both"                  # "sft" | "reward" | "both"
        self._min_gate_pass_rate = 0.0

    # ------------------------------------------------------------------
    # PluginBase
    # ------------------------------------------------------------------

    def manifest(self) -> PluginManifest:
        from config import PACE_VERSION

        return PluginManifest(
            name="pace-data-export-hook",
            version=PACE_VERSION,
            plugin_type="hook",
            pace_version_min="2.2.0",
            description="Exports shipped story traces to a JSONL training corpus for LLM fine-tuning.",
            author="PACE Framework",
            subscribed_events=["day_shipped"],
        )

    def configure(self, config: dict[str, Any]) -> None:
        if "output_dir" in config:
            self._output_dir = Path(config["output_dir"])
        if "format" in config:
            fmt = config["format"]
            if fmt not in ("sft", "reward", "both"):
                raise ValueError(f"training.format must be 'sft', 'reward', or 'both'; got '{fmt}'")
            self._format = fmt
        if "min_gate_pass_rate" in config:
            rate = float(config["min_gate_pass_rate"])
            if not 0.0 <= rate <= 1.0:
                raise ValueError(f"training.min_gate_pass_rate must be in [0.0, 1.0]; got {rate}")
            self._min_gate_pass_rate = rate

    # ------------------------------------------------------------------
    # HookBase
    # ------------------------------------------------------------------

    def on_event(self, event: str, payload: dict[str, Any]) -> None:
        if event != "day_shipped":
            return

        day: int = payload.get("day", 0)
        pace_dir: Path = payload.get("pace_dir", Path(".pace"))
        day_dir = pace_dir / f"day-{day}"

        self._export_day(day, day_dir)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _export_day(self, day: int, day_dir: Path) -> None:
        from training.collector import collect_story_trace
        from training.exporter import export_reward_jsonl, export_sft_jsonl

        trace = collect_story_trace(day_dir)
        if trace is None:
            print(f"[DataExportHook] Day {day}: no complete trace found — skipping export")
            return

        if trace.gate_pass_rate < self._min_gate_pass_rate:
            print(
                f"[DataExportHook] Day {day}: gate_pass_rate {trace.gate_pass_rate:.2f} "
                f"< min {self._min_gate_pass_rate:.2f} — skipping export"
            )
            return

        written_sft = written_reward = 0

        if self._format in ("sft", "both"):
            sft_path = self._output_dir / "sft_corpus.jsonl"
            written_sft = export_sft_jsonl([trace], sft_path, append=True)

        if self._format in ("reward", "both"):
            reward_path = self._output_dir / "reward_corpus.jsonl"
            written_reward = export_reward_jsonl([trace], reward_path, append=True)

        parts: list[str] = []
        if written_sft:
            parts.append(f"sft={written_sft}")
        if written_reward:
            parts.append(f"reward={written_reward}")
        label = ", ".join(parts) if parts else "0"
        print(
            f"[DataExportHook] Day {day}: exported trace "
            f"(reward={trace.reward_score:.3f}, gate={trace.gate_pass_rate:.2f}) "
            f"→ {self._output_dir}/ [{label} line(s)]"
        )
