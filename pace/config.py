"""PACE Framework configuration loader.

Reads pace.config.yaml and exposes a PaceConfig dataclass used by all agents.
Call load_config() once per agent invocation — it is fast (cached after first call).
"""

from __future__ import annotations

PACE_VERSION = "2.0.0"

import os
import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from functools import lru_cache


def _interpolate_env(value: str) -> str:
    """Replace ``${VAR_NAME}`` patterns with environment variable values.

    Unknown variables are left as-is so the caller can detect misconfiguration.
    """
    if not isinstance(value, str):
        return value
    return re.sub(r"\$\{([^}]+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), value)

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
class LLMLimitsConfig:
    """Per-agent-class token limits.

    Coding agents (FORGE, SCRIBE) need much larger context windows than
    analysis agents (PRIME, GATE, SENTINEL, CONDUIT) because they must hold
    full file contents and multi-iteration conversation history.
    """
    forge_input_tokens: int = 160000    # FORGE/SCRIBE: system prompt + tools + files + history
    forge_output_tokens: int = 16384    # FORGE writes complete files; prevents mid-impl truncation
    analysis_input_tokens: int = 80000  # PRIME/GATE/SENTINEL/CONDUIT: story context, not codebases
    analysis_output_tokens: int = 8192  # structured analysis responses are shorter


@dataclass
class LLMConfig:
    provider: str           # "anthropic" | "litellm"
    model: str              # model ID for FORGE/SCRIBE (e.g. "claude-sonnet-4-6")
    analysis_model: str     # model ID for PRIME/GATE/SENTINEL/CONDUIT — defaults to model
    base_url: str | None    # optional endpoint override (e.g. for Ollama)
    limits: LLMLimitsConfig = None  # type: ignore[assignment]  # per-agent-class token limits

    def __post_init__(self) -> None:
        if self.limits is None:
            self.limits = LLMLimitsConfig()


@dataclass
class ReleaseConfig:
    name: str               # Release version/name (e.g. "v2.0", "q1-2026")
    release_days: int = 90  # Total calendar days in the release
    sprint_days: int = 7    # Days per sprint (1–release_days)


@dataclass
class CostControlConfig:
    max_story_ac: int = 5         # trigger PRIME refinement if AC count exceeds this (0 = disabled)
    max_story_cost_usd: float = 0.0  # trigger PRIME refinement if SCOPE predicts more (0 = disabled)


@dataclass
class ForgeConfig:
    tdd_enforcement: bool = True  # mandatory 4-phase TDD with confirm_red_phase gate
    coverage_rule: bool = True    # every production file created/modified must have tests
    max_iterations: int = 35      # safety limit on the agentic tool-use loop


@dataclass
class UpdatesConfig:
    auto_update: bool = True        # apply update automatically when no customizations found
    suppress_warning: bool = False  # silence the customization WARNING
    channel: str = "stable"        # "stable" | "beta"


@dataclass
class CronConfig:
    """Centralized cron schedule for all PACE pipelines.

    Used by ci_generator.py to regenerate workflow files when schedules change.
    All cron expressions are 5-field POSIX format (minute hour dom month dow).
    """
    pace_pipeline: str = "0 9 * * 1-5"    # main daily cycle (weekdays at 09:00 UTC)
    planner_pipeline: str = "0 8 * * 1"   # weekly re-plan (Monday at 08:00 UTC)
    update_check: str = "0 0 * * *"       # daily update check (midnight UTC)
    timezone: str = "UTC"                 # IANA timezone used when interpreting schedules


@dataclass
class PluginEntryConfig:
    """Configuration for one plugin in the plugins: YAML section.

    Every installed plugin that declares itself via entry points is auto-discovered;
    this section provides per-plugin settings and an enable/disable toggle.
    """
    name: str                              # Must match the plugin's PluginManifest.name
    enabled: bool = True                   # Set false to skip without uninstalling
    webhook_in_port: int | None = None     # Override the default webhook-in port (9876)
    config: dict = field(default_factory=dict)  # Plugin-specific key/value config


@dataclass
class SlackConfig:
    """Slack Incoming Webhook credentials."""
    webhook_url: str  # supports ${VAR_NAME} env interpolation


@dataclass
class TeamsConfig:
    """Microsoft Teams Incoming Webhook credentials."""
    webhook_url: str  # supports ${VAR_NAME} env interpolation


@dataclass
class EmailConfig:
    """SMTP relay credentials for email notifications."""
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None   # supports ${VAR_NAME} env interpolation
    from_addr: str = ""
    to_addrs: list[str] = field(default_factory=list)


@dataclass
class NotificationsConfig:
    """Notification channel configuration (at least one channel required to send alerts)."""
    slack: SlackConfig | None = None
    teams: TeamsConfig | None = None
    email: EmailConfig | None = None


@dataclass
class AlertRuleConfig:
    """A single alert rule: fire *channels* when *event* occurs (and optional thresholds pass)."""
    event: str                              # "hold_opened" | "story_shipped" | "cost_exceeded" | ...
    channels: list[str] = field(default_factory=list)  # ["slack"] | ["teams", "email"] | ...
    threshold_usd: float | None = None      # only fire when payload["cost_usd"] >= this
    threshold_minutes: float | None = None  # only fire when payload["elapsed_minutes"] >= this


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
    forge: ForgeConfig               # FORGE agent behaviour (TDD, coverage rule)
    advisory_push_to_issues: bool  # Whether to open issues for backlogged advisory findings
    reporter_timezone: str = "UTC"  # IANA timezone for timestamps (e.g. "America/New_York")
    release: ReleaseConfig | None = None  # v2.0 release/sprint branching model (optional)
    updates: UpdatesConfig = None  # type: ignore[assignment]  # auto-update behaviour
    cron: CronConfig = None  # type: ignore[assignment]  # CI pipeline schedules
    notifications: NotificationsConfig | None = None  # notification channel credentials
    alerts: list[AlertRuleConfig] | None = None        # alert rules (event → channels)
    plugins: list[PluginEntryConfig] | None = None     # installed plugin configurations (v2.1)

    def __post_init__(self) -> None:
        if self.updates is None:
            self.updates = UpdatesConfig()
        if self.cron is None:
            self.cron = CronConfig()

    def source_dirs_table(self) -> str:
        """Return a formatted table of source directories for use in agent system prompts."""
        lines = []
        for d in self.source_dirs:
            lines.append(f"  {d.path:<30} {d.language:<12} {d.description}")
        return "\n".join(lines) if lines else "  (no source directories configured)"

    def source_dirs_names(self) -> str:
        """Return a comma-separated list of source directory labels."""
        return ", ".join(d.name for d in self.source_dirs) if self.source_dirs else "(none)"


def _parse_notifications(raw: dict) -> NotificationsConfig | None:
    """Build a NotificationsConfig from the ``notifications:`` YAML section."""
    if not raw:
        return None

    slack: SlackConfig | None = None
    slack_raw = raw.get("slack") or {}
    if slack_raw.get("webhook_url"):
        slack = SlackConfig(webhook_url=_interpolate_env(slack_raw["webhook_url"]))

    teams: TeamsConfig | None = None
    teams_raw = raw.get("teams") or {}
    if teams_raw.get("webhook_url"):
        teams = TeamsConfig(webhook_url=_interpolate_env(teams_raw["webhook_url"]))

    email: EmailConfig | None = None
    email_raw = raw.get("email") or {}
    if email_raw.get("smtp_host"):
        to_addrs = email_raw.get("to_addrs", [])
        if isinstance(to_addrs, str):
            to_addrs = [a.strip() for a in to_addrs.split(",") if a.strip()]
        raw_pw = email_raw.get("smtp_password")
        email = EmailConfig(
            smtp_host=email_raw["smtp_host"],
            smtp_port=int(email_raw.get("smtp_port", 587)),
            smtp_user=email_raw.get("smtp_user"),
            smtp_password=_interpolate_env(str(raw_pw)) if raw_pw is not None else None,
            from_addr=email_raw.get("from_addr", ""),
            to_addrs=to_addrs,
        )

    if not any([slack, teams, email]):
        return None
    return NotificationsConfig(slack=slack, teams=teams, email=email)


def _parse_plugins(raw: list) -> list[PluginEntryConfig] | None:
    """Build a list of PluginEntryConfig from the ``plugins:`` YAML section."""
    if not raw:
        return None
    entries: list[PluginEntryConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        port_raw = item.get("webhook_in_port")
        entries.append(PluginEntryConfig(
            name=str(item["name"]),
            enabled=bool(item.get("enabled", True)),
            webhook_in_port=int(port_raw) if port_raw is not None else None,
            config=dict(item.get("config") or {}),
        ))
    return entries or None


def _parse_alerts(raw: list) -> list[AlertRuleConfig] | None:
    """Build a list of AlertRuleConfig from the ``alerts:`` YAML section."""
    if not raw:
        return None
    rules: list[AlertRuleConfig] = []
    for item in raw:
        channels = item.get("channels", [])
        if isinstance(channels, str):
            channels = [channels]
        threshold_usd = item.get("threshold_usd")
        threshold_minutes = item.get("threshold_minutes")
        rules.append(AlertRuleConfig(
            event=str(item["event"]),
            channels=list(channels),
            threshold_usd=float(threshold_usd) if threshold_usd is not None else None,
            threshold_minutes=float(threshold_minutes) if threshold_minutes is not None else None,
        ))
    return rules or None


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
    limits_raw = llm_raw.get("limits", {}) or {}
    llm_limits = LLMLimitsConfig(
        forge_input_tokens=int(limits_raw.get("forge_input_tokens", 160000)),
        forge_output_tokens=int(limits_raw.get("forge_output_tokens", 16384)),
        analysis_input_tokens=int(limits_raw.get("analysis_input_tokens", 80000)),
        analysis_output_tokens=int(limits_raw.get("analysis_output_tokens", 8192)),
    )
    llm = LLMConfig(
        provider=llm_raw.get("provider", "anthropic"),
        model=forge_model,
        analysis_model=llm_raw.get("analysis_model", forge_model),
        base_url=llm_raw.get("base_url"),
        limits=llm_limits,
    )

    cost_control = CostControlConfig(
        max_story_ac=int(cc_raw.get("max_story_ac", 5)),
        max_story_cost_usd=float(cc_raw.get("max_story_cost_usd", 0.0)),
    )

    forge_raw = raw.get("forge", {})
    forge = ForgeConfig(
        tdd_enforcement=bool(forge_raw.get("tdd_enforcement", True)),
        coverage_rule=bool(forge_raw.get("coverage_rule", True)),
        max_iterations=int(forge_raw.get("max_iterations", 35)),
    )

    release_raw = raw.get("release")
    release = (
        ReleaseConfig(
            name=str(release_raw["name"]),
            release_days=int(release_raw.get("release_days", 90)),
            sprint_days=int(release_raw.get("sprint_days", 7)),
        )
        if release_raw and release_raw.get("name")
        else None
    )

    updates_raw = raw.get("updates", {}) or {}
    updates = UpdatesConfig(
        auto_update=bool(updates_raw.get("auto_update", True)),
        suppress_warning=bool(updates_raw.get("suppress_warning", False)),
        channel=str(updates_raw.get("channel", "stable")),
    )

    cron_raw = raw.get("cron", {}) or {}
    cron = CronConfig(
        pace_pipeline=str(cron_raw.get("pace_pipeline", "0 9 * * 1-5")),
        planner_pipeline=str(cron_raw.get("planner_pipeline", "0 8 * * 1")),
        update_check=str(cron_raw.get("update_check", "0 0 * * *")),
        timezone=str(cron_raw.get("timezone", "UTC")),
    )

    notifications = _parse_notifications(raw.get("notifications") or {})
    alerts = _parse_alerts(raw.get("alerts") or [])
    plugins = _parse_plugins(raw.get("plugins") or [])

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
        forge=forge,
        advisory_push_to_issues=bool(advisory_raw.get("push_to_issues", False)),
        reporter_timezone=reporter_raw.get("timezone", "UTC"),
        release=release,
        updates=updates,
        cron=cron,
        notifications=notifications,
        alerts=alerts,
        plugins=plugins,
    )
