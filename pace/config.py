"""PACE Framework configuration loader.

Reads pace.config.yaml and exposes a PaceConfig dataclass used by all agents.
Call load_config() once per agent invocation — it is fast (cached after first call).
"""

PACE_VERSION = "1.1.0"

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from functools import lru_cache

CONFIG_FILE = Path(__file__).parent / "pace.config.yaml"
REPO_ROOT = Path(__file__).parent.parent


@dataclass
class SourceDir:
    name: str        # Short label (e.g. "core", "cli")
    path: str        # Relative path from repo root (e.g. "src/")
    language: str    # Primary language (e.g. "Python", "Go")
    description: str # One-line description


@dataclass
class TechConfig:
    primary_language: str
    secondary_language: str | None
    ci_system: str
    test_command: str
    build_command: str | None


@dataclass
class LLMConfig:
    provider: str        # "anthropic" | "litellm"
    model: str           # model ID for FORGE/SCRIBE (e.g. "claude-sonnet-4-6")
    analysis_model: str  # model ID for PRIME/GATE/SENTINEL/CONDUIT — defaults to model
    base_url: str | None # optional endpoint override (e.g. for Ollama)


@dataclass
class CostControlConfig:
    max_story_ac: int = 5         # trigger PRIME refinement if AC count exceeds this (0 = disabled)
    max_story_cost_usd: float = 0.0  # trigger PRIME refinement if SCOPE predicts more (0 = disabled)


@dataclass
class PaceConfig:
    product_name: str
    product_description: str
    github_org: str
    sprint_duration_days: int
    source_dirs: list[SourceDir]
    docs_dir: Path | None       # Absolute path to external docs folder, or None
    tech: TechConfig
    ci_type: str                # "github" | "gitlab" | "bitbucket" | "jenkins" | "local"
    tracker_type: str           # "jira" | "github" | "gitlab" | "bitbucket" | "local"
    llm: LLMConfig
    cost_control: CostControlConfig  # Proactive story scoping thresholds
    advisory_push_to_issues: bool  # Whether to open issues for backlogged advisory findings
    reporter_timezone: str = "UTC"  # IANA timezone for timestamps (e.g. "America/New_York")

    def source_dirs_table(self) -> str:
        """Return a formatted table of source directories for use in agent system prompts."""
        lines = []
        for d in self.source_dirs:
            lines.append(f"  {d.path:<30} {d.language:<12} {d.description}")
        return "\n".join(lines) if lines else "  (no source directories configured)"

    def source_dirs_names(self) -> str:
        """Return a comma-separated list of source directory labels."""
        return ", ".join(d.name for d in self.source_dirs) if self.source_dirs else "(none)"


@lru_cache(maxsize=1)
def load_config() -> PaceConfig:
    """Load and return the PaceConfig. Cached — safe to call multiple times."""
    with open(CONFIG_FILE) as f:
        raw = yaml.safe_load(f)

    product = raw.get("product", {})
    sprint = raw.get("sprint", {})
    source = raw.get("source", {})
    tech_raw = raw.get("tech", {})

    source_dirs = [
        SourceDir(
            name=d["name"],
            path=d["path"],
            language=d.get("language", ""),
            description=d.get("description", ""),
        )
        for d in source.get("dirs", [])
    ]

    # Resolve docs_dir: absolute as-is, relative resolved from REPO_ROOT
    raw_docs_dir = source.get("docs_dir")
    if raw_docs_dir:
        p = Path(raw_docs_dir)
        docs_dir = p if p.is_absolute() else (REPO_ROOT / p).resolve()
    else:
        docs_dir = None

    tech = TechConfig(
        primary_language=tech_raw.get("primary_language", "Python 3.12"),
        secondary_language=tech_raw.get("secondary_language"),
        ci_system=tech_raw.get("ci_system", "GitHub Actions"),
        test_command=tech_raw.get("test_command", "pytest -v --tb=short"),
        build_command=tech_raw.get("build_command"),
    )

    platform_raw = raw.get("platform", {})
    advisory_raw = raw.get("advisory", {})
    reporter_raw = raw.get("reporter", {})
    llm_raw = raw.get("llm", {})
    cc_raw = raw.get("cost_control", {})

    forge_model = llm_raw.get("model", "claude-sonnet-4-6")
    llm = LLMConfig(
        provider=llm_raw.get("provider", "anthropic"),
        model=forge_model,
        analysis_model=llm_raw.get("analysis_model", forge_model),
        base_url=llm_raw.get("base_url"),
    )

    cost_control = CostControlConfig(
        max_story_ac=int(cc_raw.get("max_story_ac", 5)),
        max_story_cost_usd=float(cc_raw.get("max_story_cost_usd", 0.0)),
    )

    return PaceConfig(
        product_name=product.get("name", "My Product"),
        product_description=str(product.get("description", "")).strip(),
        github_org=product.get("github_org", ""),
        sprint_duration_days=sprint.get("duration_days", 30),
        source_dirs=source_dirs,
        docs_dir=docs_dir,
        tech=tech,
        ci_type=platform_raw.get("ci") or platform_raw.get("type", "github"),
        tracker_type=platform_raw.get("tracker") or platform_raw.get("type", "github"),
        llm=llm,
        cost_control=cost_control,
        advisory_push_to_issues=bool(advisory_raw.get("push_to_issues", False)),
        reporter_timezone=reporter_raw.get("timezone", "UTC"),
    )
