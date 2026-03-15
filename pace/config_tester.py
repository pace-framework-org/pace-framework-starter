"""PACE Configuration Tester.

Validates pace.config.yaml before any agent is invoked. Designed to run as the
first step in every PACE pipeline so misconfigurations are caught early rather
than mid-sprint.

Exit codes:
    0 — clean (no errors, no warnings)
    1 — warnings found (no hard errors)
    2 — one or more hard errors found

Usage:
    python pace/config_tester.py
    python pace/config_tester.py --json          # machine-readable output for CI
    python pace/config_tester.py --config path/to/pace.config.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

CONFIG_FILE = Path(__file__).parent / "pace.config.yaml"

# ---------------------------------------------------------------------------
# Known valid identifiers
# ---------------------------------------------------------------------------

_KNOWN_ANTHROPIC_MODELS = {
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
}
_OPUS_CLASS_MODELS = {"claude-opus-4-6", "claude-3-opus-20240229"}
_VALID_CI_TYPES = {"github", "gitlab", "bitbucket", "jenkins", "local"}
_VALID_TRACKER_TYPES = {"jira", "github", "gitlab", "bitbucket", "local"}
_VALID_PROVIDERS = {"anthropic", "litellm"}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ConfigTestResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def suggest(self, msg: str) -> None:
        self.suggestions.append(msg)

    @property
    def exit_code(self) -> int:
        if self.errors:
            return 2
        if self.warnings:
            return 1
        return 0

    def to_dict(self) -> dict:
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "suggestions": self.suggestions,
            "exit_code": self.exit_code,
        }


# ---------------------------------------------------------------------------
# Section validators
# ---------------------------------------------------------------------------

def _validate_product(raw: dict, r: ConfigTestResult) -> None:
    product = raw.get("product", {})
    name = product.get("name", "")
    if not name or name == "My Product":
        r.error("product.name is required and must not be the placeholder 'My Product'")
    org = product.get("github_org", "")
    if not org or org == "my-org":
        platform = raw.get("platform", {})
        ci = platform.get("ci") or platform.get("type", "github")
        tracker = platform.get("tracker") or platform.get("type", "github")
        if ci == "github" or tracker == "github":
            r.error(
                "product.github_org is required when platform.ci or platform.tracker is 'github'"
            )
        else:
            r.suggest(
                "product.github_org is not set; required if you switch to GitHub CI/tracker"
            )
    if not str(product.get("description", "")).strip():
        r.suggest(
            "product.description is empty — all agents inject it into their system prompt; "
            "add a 1–2 sentence description of what the product does"
        )


def _validate_sprint(raw: dict, r: ConfigTestResult) -> None:
    sprint = raw.get("sprint", {})
    duration = sprint.get("duration_days", 30)
    if not isinstance(duration, int) or duration <= 0:
        r.error(f"sprint.duration_days must be a positive integer, got: {duration!r}")
    # Cross-check with release if present
    release = raw.get("release", {})
    if release:
        sprint_days = release.get("sprint_days", 7)
        release_days = release.get("release_days", 90)
        if (
            isinstance(sprint_days, int) and isinstance(release_days, int)
            and sprint_days > release_days
        ):
            r.warn(
                f"release.sprint_days ({sprint_days}) > release.release_days ({release_days}) — "
                "a sprint cannot be longer than the release"
            )


def _validate_release(raw: dict, r: ConfigTestResult) -> None:
    release = raw.get("release")
    if release is None:
        r.suggest(
            "release section is not configured; PACE v2.0 supports a full "
            "release/sprint branching model — see ROADMAP.md Item 1"
        )
        return
    if not release.get("name"):
        r.error("release.name is required when release section is present")
    release_days = release.get("release_days", 0)
    sprint_days = release.get("sprint_days", 0)
    if not isinstance(release_days, int) or release_days <= 0:
        r.error(f"release.release_days must be a positive integer, got: {release_days!r}")
    if not isinstance(sprint_days, int) or sprint_days <= 0:
        r.error(f"release.sprint_days must be a positive integer, got: {sprint_days!r}")


def _validate_source(raw: dict, r: ConfigTestResult) -> None:
    source = raw.get("source", {})
    dirs = source.get("dirs", [])
    if not dirs:
        r.error(
            "source.dirs is empty — FORGE requires at least one directory entry "
            "specifying where to write code"
        )
        return
    for i, d in enumerate(dirs):
        if not d.get("name"):
            r.error(f"source.dirs[{i}].name is required")
        if not d.get("path"):
            r.error(f"source.dirs[{i}].path is required")
        elif not str(d["path"]).endswith("/"):
            r.warn(
                f"source.dirs[{i}].path '{d['path']}' does not end with '/' — "
                "convention is to include a trailing slash"
            )
    docs_dir = source.get("docs_dir")
    if docs_dir:
        p = (
            Path(docs_dir)
            if Path(docs_dir).is_absolute()
            else (Path(__file__).parent.parent / docs_dir).resolve()
        )
        if not p.exists():
            r.warn(
                f"source.docs_dir '{docs_dir}' resolved to '{p}' which does not exist; "
                "SCRIBE will skip external docs"
            )


def _validate_tech(raw: dict, r: ConfigTestResult) -> None:
    tech = raw.get("tech", {})
    if not tech.get("primary_language"):
        r.error("tech.primary_language is required — agents use it to select language conventions")
    test_cmd = tech.get("test_command", "")
    if not test_cmd:
        r.warn(
            "tech.test_command is not set — GATE will not know how to run the test suite"
        )
    elif test_cmd in ("pytest -v --tb=short", "pytest"):
        r.suggest(
            "tech.test_command uses the default Python command — update if your project "
            "uses a different test runner (e.g. 'go test ./...' or 'npm test')"
        )


def _validate_platform(raw: dict, r: ConfigTestResult) -> None:
    platform = raw.get("platform", {})
    ci = platform.get("ci") or platform.get("type", "github")
    tracker = platform.get("tracker") or platform.get("type", "github")
    if ci not in _VALID_CI_TYPES:
        r.error(
            f"platform.ci '{ci}' is not valid. Supported: {', '.join(sorted(_VALID_CI_TYPES))}"
        )
    if tracker not in _VALID_TRACKER_TYPES:
        r.error(
            f"platform.tracker '{tracker}' is not valid. "
            f"Supported: {', '.join(sorted(_VALID_TRACKER_TYPES))}"
        )
    advisory = raw.get("advisory", {})
    if advisory.get("push_to_issues") and tracker == "local":
        r.warn(
            "advisory.push_to_issues is true but platform.tracker is 'local' — "
            "no issue tracker is configured to receive advisory findings"
        )


def _validate_llm(raw: dict, r: ConfigTestResult) -> None:
    llm = raw.get("llm", {})
    provider = llm.get("provider", "anthropic")
    if provider not in _VALID_PROVIDERS:
        r.error(
            f"llm.provider '{provider}' is not valid. "
            f"Supported: {', '.join(sorted(_VALID_PROVIDERS))}"
        )
    model = llm.get("model", "")
    if not model:
        r.error("llm.model is required")
    elif provider == "anthropic" and model not in _KNOWN_ANTHROPIC_MODELS:
        r.warn(
            f"llm.model '{model}' is not in the known Anthropic model list "
            f"({', '.join(sorted(_KNOWN_ANTHROPIC_MODELS))}). "
            "This warning fires for recently released models — ignore if the model ID is correct."
        )
    analysis_model = llm.get("analysis_model") or model
    if not analysis_model:
        r.suggest(
            "llm.analysis_model is not set — defaults to llm.model; "
            "set to claude-haiku-4-5-20251001 for 4–5× cheaper analysis calls "
            "(PRIME, GATE, SENTINEL, CONDUIT)"
        )
    elif provider == "anthropic" and analysis_model in _OPUS_CLASS_MODELS:
        r.warn(
            f"llm.analysis_model is set to opus-class model '{analysis_model}'; "
            "analysis agents (PRIME, GATE, SENTINEL, CONDUIT) perform well with Haiku "
            "at significantly lower cost"
        )


def _validate_llm_limits(raw: dict, r: ConfigTestResult) -> None:
    llm = raw.get("llm", {})
    limits = llm.get("limits")
    if limits is None:
        r.suggest(
            "llm.limits is not configured; per-agent token limits are recommended. "
            "For FORGE on non-trivial codebases, set forge_input_tokens: 160000 to prevent "
            "context truncation at iteration 10+. See ROADMAP.md Item 3."
        )
        return
    forge_input = limits.get("forge_input_tokens", 160000)
    if isinstance(forge_input, int) and forge_input < 32000:
        r.warn(
            f"llm.limits.forge_input_tokens is {forge_input} — too low for FORGE on "
            "any non-trivial codebase; a single file read + conversation history "
            "regularly exceeds 32k tokens by iteration 10. Recommended minimum: 100000."
        )


def _validate_forge(raw: dict, r: ConfigTestResult) -> None:
    forge = raw.get("forge", {})
    max_iter = forge.get("max_iterations", 35)
    if not isinstance(max_iter, int) or max_iter < 1:
        r.error(f"forge.max_iterations must be a positive integer, got: {max_iter!r}")
    elif max_iter < 10:
        r.warn(
            f"forge.max_iterations is {max_iter} — very low; FORGE may exhaust iterations "
            "before completing even simple stories"
        )
    elif max_iter > 200:
        r.warn(
            f"forge.max_iterations is {max_iter} — unusually high; "
            "per-story cost could be very large"
        )


def _validate_cost_control(raw: dict, r: ConfigTestResult) -> None:
    cc = raw.get("cost_control", {})
    max_cost = cc.get("max_story_cost_usd", 0.0)
    if isinstance(max_cost, (int, float)) and 0 < float(max_cost) < 0.10:
        r.warn(
            f"cost_control.max_story_cost_usd is ${float(max_cost):.2f} — extremely low; "
            "a single SCOPE pre-check call costs ~$0.01 and FORGE typically costs $0.50+ "
            "per story minimum. PRIME refinement will trigger on almost every story."
        )
    max_ac = cc.get("max_story_ac", 5)
    if isinstance(max_ac, int) and max_ac < 2:
        r.warn(
            f"cost_control.max_story_ac is {max_ac} — too low to write meaningful stories; "
            "most stories need at least 2–3 acceptance criteria"
        )


_KNOWN_ALERT_EVENTS = {
    "hold_opened",
    "story_shipped",
    "cost_exceeded",
    "pipeline_lock_timeout",
    "update_available",
}
_KNOWN_CHANNELS = {"slack", "teams", "email"}


def _validate_notifications(raw: dict, r: ConfigTestResult) -> None:
    notif = raw.get("notifications") or {}
    alerts = raw.get("alerts") or []

    if not notif and not alerts:
        r.suggest(
            "notifications and alerts are not configured; PACE v2.0 supports Slack/Teams/email "
            "alerts for hold_opened, story_shipped, cost_exceeded and more — see ROADMAP.md Item 5"
        )
        return

    # Determine which channels are actually configured
    configured_channels: set[str] = set()

    if notif.get("slack", {}) and notif["slack"].get("webhook_url"):
        configured_channels.add("slack")
    if notif.get("teams", {}) and notif["teams"].get("webhook_url"):
        configured_channels.add("teams")
    email_raw = notif.get("email", {}) or {}
    if email_raw.get("smtp_host"):
        configured_channels.add("email")
        if not email_raw.get("to_addrs"):
            r.error("notifications.email.to_addrs must have at least one recipient address")
        smtp_port = email_raw.get("smtp_port", 587)
        if not isinstance(smtp_port, int) or smtp_port < 1 or smtp_port > 65535:
            r.error(f"notifications.email.smtp_port must be an integer 1–65535, got: {smtp_port!r}")

    if notif and not configured_channels:
        r.warn(
            "notifications section is present but no channel (slack/teams/email) is fully configured; "
            "alerts will be silently dropped"
        )

    # Validate alert rules
    for i, rule in enumerate(alerts):
        if not isinstance(rule, dict):
            r.error(f"alerts[{i}] must be a mapping (event/channels/thresholds)")
            continue
        event = rule.get("event")
        if not event:
            r.error(f"alerts[{i}].event is required")
        elif event not in _KNOWN_ALERT_EVENTS:
            r.warn(
                f"alerts[{i}].event '{event}' is not one of the known events "
                f"({', '.join(sorted(_KNOWN_ALERT_EVENTS))}); "
                "it will only fire if a matching event is fired by the orchestrator"
            )
        channels = rule.get("channels", [])
        if isinstance(channels, str):
            channels = [channels]
        if not channels:
            r.warn(f"alerts[{i}] (event={event!r}) has no channels — alert will be a no-op")
        for ch in channels:
            if ch not in _KNOWN_CHANNELS:
                r.error(
                    f"alerts[{i}].channels: '{ch}' is not a supported channel "
                    f"(supported: {', '.join(sorted(_KNOWN_CHANNELS))})"
                )
            elif ch not in configured_channels:
                r.warn(
                    f"alerts[{i}].channels references '{ch}' but notifications.{ch} "
                    "is not configured — alert will be silently dropped for this channel"
                )

    if alerts and not notif:
        r.warn(
            "alerts are configured but notifications section is missing; "
            "no channel credentials are available and all alerts will be dropped"
        )


def _validate_plugins(raw: dict, r: ConfigTestResult) -> None:
    plugins = raw.get("plugins")
    if not plugins:
        return

    if not isinstance(plugins, list):
        r.error("plugins must be a list of plugin entries")
        return

    from importlib.metadata import entry_points, packages_distributions

    # Discover installed plugin manifests from entry points
    installed_names: dict[str, str] = {}  # name → version (best-effort)
    _PLUGIN_GROUPS = [
        "pace.plugins.agents", "pace.plugins.tools", "pace.plugins.adapters",
        "pace.plugins.hooks", "pace.plugins.webhooks_in", "pace.plugins.webhooks_out",
    ]
    for group in _PLUGIN_GROUPS:
        try:
            for ep in entry_points(group=group):
                try:
                    klass = ep.load()
                    instance = klass()
                    m = instance.manifest()
                    installed_names[m.name] = m.version
                except Exception as e:
                    r.warn(f"Failed to inspect plugin entry point '{ep.name}' in group '{group}': {e}")
        except Exception as e:
            r.warn(f"Failed to scan plugin entry point group '{group}': {e}")

    from config import PACE_VERSION

    def _ver_compat(current: str, min_v: str, max_v: str | None) -> bool:
        try:
            def _t(v: str) -> tuple[int, ...]:
                return tuple(int(x) for x in v.split(".")[:3])
            cur = _t(current)
            return _t(min_v) <= cur and (max_v is None or cur <= _t(max_v))
        except Exception:
            return True

    seen_names: set[str] = set()
    for i, item in enumerate(plugins):
        if not isinstance(item, dict):
            r.error(f"plugins[{i}] must be a mapping (name/enabled/config)")
            continue
        name = item.get("name")
        if not name:
            r.error(f"plugins[{i}].name is required")
            continue
        if name in seen_names:
            r.warn(f"plugins: duplicate entry for plugin '{name}'")
        seen_names.add(name)

        port = item.get("webhook_in_port")
        if port is not None and (not isinstance(port, int) or not (1 <= port <= 65535)):
            r.error(f"plugins[{i}] ({name}): webhook_in_port must be an integer 1–65535, got: {port!r}")

        if name not in installed_names:
            r.warn(
                f"plugins[{i}] references '{name}' which is not installed "
                "(no matching pace.plugins.* entry point found); "
                "run: pip install <plugin-package>"
            )

    # Check installed plugins for PACE version compatibility
    for ep_group in _PLUGIN_GROUPS:
        try:
            for ep in entry_points(group=ep_group):
                try:
                    klass = ep.load()
                    instance = klass()
                    m = instance.manifest()
                    if not _ver_compat(PACE_VERSION, m.pace_version_min, m.pace_version_max):
                        r.warn(
                            f"Installed plugin '{m.name}' requires PACE "
                            f"{m.pace_version_min}"
                            + (f"–{m.pace_version_max}" if m.pace_version_max else "+")
                            + f" but PACE_VERSION is {PACE_VERSION}; "
                            "plugin will be skipped at runtime"
                        )
                except Exception as e:
                    r.warn(
                        f"Failed to inspect plugin entry point '{ep.name}' in group "
                        f"'{ep_group}' for PACE version compatibility: {e}"
                    )
        except Exception as e:
            r.warn(f"Failed to scan plugin entry point group '{ep_group}' for compatibility: {e}")


def _validate_cron(raw: dict, r: ConfigTestResult) -> None:
    cron = raw.get("cron")
    if cron is None:
        r.suggest(
            "cron section is not configured; PACE v2.0 supports centralised cron scheduling "
            "with concurrency guards — see ROADMAP.md Item 8"
        )
        return
    import re
    cron_re = re.compile(r"^(\S+\s+){4}\S+$")
    for key in ("pace_pipeline", "planner_pipeline", "update_check"):
        val = cron.get(key)
        if val and not cron_re.match(str(val).strip()):
            r.error(
                f"cron.{key} '{val}' does not look like a valid cron expression "
                "(expected 5 space-separated fields, e.g. '0 9 * * 1-5')"
            )


def _validate_reporter(raw: dict, r: ConfigTestResult) -> None:
    reporter = raw.get("reporter", {})
    tz = reporter.get("timezone", "UTC")
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(tz)
    except Exception:
        r.warn(
            f"reporter.timezone '{tz}' may not be a valid IANA timezone — "
            "timestamps in PROGRESS.md and job summaries could be incorrect"
        )


def _validate_training(raw: dict, r: ConfigTestResult) -> None:
    """Validate the training: section (v2.2 Training Data Pipeline)."""
    training = raw.get("training")
    if training is None:
        # Not configured — that is fine; defaults will be used.
        return

    if not isinstance(training, dict):
        r.error("training must be a YAML mapping (key: value pairs)")
        return

    # format
    fmt = training.get("format", "both")
    if fmt not in ("sft", "reward", "both"):
        r.error(
            f"training.format '{fmt}' is not valid; "
            "supported values: 'sft', 'reward', 'both'"
        )

    # min_gate_pass_rate
    rate = training.get("min_gate_pass_rate")
    if rate is not None:
        try:
            rate_f = float(rate)
            if not 0.0 <= rate_f <= 1.0:
                r.error(
                    f"training.min_gate_pass_rate {rate_f} is out of range; "
                    "must be between 0.0 and 1.0 (inclusive)"
                )
        except (TypeError, ValueError):
            r.error(f"training.min_gate_pass_rate '{rate}' must be a number")

    # output_dir — warn if it looks absolute and unusual
    output_dir = training.get("output_dir", "training_data")
    if output_dir and str(output_dir).startswith("/"):
        r.suggest(
            f"training.output_dir '{output_dir}' is an absolute path; "
            "consider a relative path so the corpus stays portable with the repo"
        )

    # export_on_ship
    export = training.get("export_on_ship", True)
    if not isinstance(export, bool):
        r.warn(
            f"training.export_on_ship should be true or false (boolean); "
            f"got '{export}' — will be coerced"
        )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_config_test(config_file: Path = CONFIG_FILE) -> ConfigTestResult:
    """Load and validate pace.config.yaml. Returns a ConfigTestResult.

    Safe to call multiple times (creates a fresh result each time).
    """
    r = ConfigTestResult()

    if not config_file.exists():
        r.error(f"Configuration file not found: {config_file}")
        return r

    try:
        with open(config_file) as f:
            raw = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        r.error(f"YAML parse error in {config_file}: {exc}")
        return r

    _validate_product(raw, r)
    _validate_sprint(raw, r)
    _validate_release(raw, r)
    _validate_source(raw, r)
    _validate_tech(raw, r)
    _validate_platform(raw, r)
    _validate_llm(raw, r)
    _validate_llm_limits(raw, r)
    _validate_forge(raw, r)
    _validate_cost_control(raw, r)
    _validate_notifications(raw, r)
    _validate_plugins(raw, r)
    _validate_cron(raw, r)
    _validate_reporter(raw, r)
    _validate_training(raw, r)

    return r


def _print_result(r: ConfigTestResult, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(r.to_dict(), indent=2))
        return

    if not r.errors and not r.warnings and not r.suggestions:
        print("✓ pace.config.yaml is valid — no errors, warnings, or suggestions.")
        return

    if r.errors:
        print(f"\n[ERRORS] {len(r.errors)} error(s) — must be fixed before running PACE:\n")
        for e in r.errors:
            print(f"  ✗  {e}")

    if r.warnings:
        print(f"\n[WARNINGS] {len(r.warnings)} warning(s) — review before running:\n")
        for w in r.warnings:
            print(f"  ⚠  {w}")

    if r.suggestions:
        print(f"\n[SUGGESTIONS] {len(r.suggestions)} suggestion(s):\n")
        for s in r.suggestions:
            print(f"  →  {s}")

    print()
    if r.errors:
        print(
            f"Config test FAILED — {len(r.errors)} error(s). "
            "Fix all errors above before running any PACE pipeline."
        )
    elif r.warnings:
        print(f"Config test PASSED WITH WARNINGS — {len(r.warnings)} warning(s). Review before running.")
    else:
        print("Config test passed — suggestions only (no errors or warnings).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="PACE Configuration Tester — validates pace.config.yaml"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results as JSON (for CI integration)"
    )
    parser.add_argument(
        "--config",
        default=str(CONFIG_FILE),
        metavar="PATH",
        help="Path to pace.config.yaml (default: pace/pace.config.yaml)",
    )
    args = parser.parse_args()

    result = run_config_test(Path(args.config))
    _print_result(result, as_json=args.json)
    sys.exit(result.exit_code)
