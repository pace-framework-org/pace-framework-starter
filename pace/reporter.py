"""PACE Reporter — writes job summaries and updates PROGRESS.md after each cycle."""

import os
import sys
import yaml
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from advisory import load_open_backlog
from config import load_config

REPO_ROOT = Path(__file__).parent.parent
PACE_DIR = REPO_ROOT / ".pace"
PROGRESS_FILE = REPO_ROOT / "PROGRESS.md"
PLAN_FILE = Path(__file__).parent / "plan.yaml"

RESULT_ICON = {"SHIP": "✅", "HOLD": "🔴", "ABORT": "⚠️", "PENDING": "⏳", "PLAN": "📋"}


def _load_update_status() -> dict | None:
    """Return update status dict from .pace/update_status.yaml, or None if absent."""
    status_file = PACE_DIR / "update_status.yaml"
    if not status_file.exists():
        return None
    try:
        import json as _json
        return _json.loads(status_file.read_text())
    except Exception:
        return None


def _load_plan() -> dict:
    with open(PLAN_FILE) as f:
        return yaml.safe_load(f)


def _load_planner_report() -> dict | None:
    """Load the Day 0 planner report from .pace/day-0/planner.md, or None if absent."""
    planner_file = PACE_DIR / "day-0" / "planner.md"
    if not planner_file.exists():
        return None
    return yaml.safe_load(planner_file.read_text()) or None


def _load_plan_estimates() -> dict[int, dict]:
    """Return {day: estimate_dict} from the Day 0 planner report."""
    report = _load_planner_report()
    if not report:
        return {}
    return {e["day"]: e for e in report.get("estimates", [])}


def _load_forge_cost(day: int) -> float | None:
    """Return forge_cost_usd from a day's handoff.md, or None if not available."""
    handoff_file = PACE_DIR / f"day-{day}" / "handoff.md"
    if not handoff_file.exists():
        return None
    data = yaml.safe_load(handoff_file.read_text()) or {}
    cost = data.get("forge_cost_usd")
    return float(cost) if cost is not None else None


def _load_attempts(day: int) -> list[dict]:
    """Return all run-attempt records for a day from attempts.yaml, or []."""
    f = PACE_DIR / f"day-{day}" / "attempts.yaml"
    if not f.exists():
        return []
    return yaml.safe_load(f.read_text()) or []


def _load_total_cost(day: int) -> tuple[float | None, int]:
    """Return (total_cost_usd_across_all_runs, run_count).

    When attempts.yaml exists, sums every run (including failed retries).
    Falls back to cycle.md / handoff.md for days before this feature.
    """
    attempts = _load_attempts(day)
    if attempts:
        total = round(sum(float(a.get("cost_usd", 0.0)) for a in attempts), 4)
        return total, len(attempts)
    cost = _load_cycle_cost(day)
    return cost, (1 if cost is not None else 0)


def _load_cycle_cost(day: int) -> float | None:
    """Return total pipeline cost for a day (PRIME+FORGE+GATE+SENTINEL+CONDUIT).

    Reads cycle.md written since v1.2.0. Falls back to forge_cost_usd for
    pre-v1.2.0 artifacts so old sprints render correctly.
    """
    cycle_file = PACE_DIR / f"day-{day}" / "cycle.md"
    if cycle_file.exists():
        data = yaml.safe_load(cycle_file.read_text()) or {}
        cost = data.get("cycle_cost_usd")
        if cost is not None:
            return float(cost)
    return _load_forge_cost(day)


def _load_day_artifacts(day: int) -> tuple[dict | None, dict | None, dict | None]:
    """Return (story_card, handoff, gate_report) for a given day, or None if missing."""
    day_dir = PACE_DIR / f"day-{day}"
    story, handoff, gate = None, None, None
    if (day_dir / "story.md").exists():
        story = yaml.safe_load((day_dir / "story.md").read_text())
    if (day_dir / "handoff.md").exists():
        handoff = yaml.safe_load((day_dir / "handoff.md").read_text())
    if (day_dir / "gate.md").exists():
        gate = yaml.safe_load((day_dir / "gate.md").read_text())
    return story, handoff, gate


def _count_stats(max_day: int) -> dict:
    shipped, held, aborted, deferred_total, escalated = 0, 0, 0, 0, 0
    for d in range(1, max_day + 1):
        _, _, gate = _load_day_artifacts(d)
        if gate is None:
            continue
        decision = gate.get("gate_decision")
        if decision == "SHIP":
            shipped += 1
            deferred_total += len(gate.get("deferred", []))
        elif decision == "HOLD":
            held += 1
        escalation_file = PACE_DIR / f"day-{d}" / "escalated"
        if escalation_file.exists():
            escalated += 1
    return {
        "shipped": shipped,
        "held": held,
        "deferred": deferred_total,
        "escalated": escalated,
    }


def write_job_summary(
    day: int,
    outcome: str,
    story_card: dict | None,
    gate_report: dict | None,
    sentinel_report: dict | None = None,
    conduit_report: dict | None = None,
    abort_reason: str = "",
    ci=None,
) -> None:
    """Build the job summary markdown and deliver it via the CI adapter.

    If ci is None, falls back to writing $GITHUB_STEP_SUMMARY directly
    (backward-compatible with GitHub Actions without an adapter).
    """

    cfg = load_config()
    icon = RESULT_ICON.get(outcome, "❓")
    tz = ZoneInfo(cfg.reporter_timezone)
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M %Z")
    stats = _count_stats(day)
    total_days = cfg.sprint_duration_days
    ship_rate = f"{(stats['shipped'] / day * 100):.0f}%" if day > 0 else "N/A"

    lines = [
        f"# PACE Day {day} — {icon} {outcome}",
        f"",
        f"**Product:** {cfg.product_name}  ",
        f"**Run time:** {now}  ",
        f"**Overall progress:** {stats['shipped']}/{day} days shipped ({ship_rate} SHIP rate)",
        f"",
    ]

    if outcome == "ABORT":
        lines += [
            f"## ⚠️ Cycle Aborted — Infrastructure Failure",
            f"",
            f"```",
            abort_reason[:1000],
            f"```",
            f"",
            f"> This is not a FORGE/GATE hold. Fix the underlying issue and re-run Day {day}.",
        ]
    else:
        if story_card:
            lines += [
                f"## Story Card",
                f"",
                f"**{story_card.get('story', 'N/A')}**",
                f"",
                f"| Field | Value |",
                f"| --- | --- |",
                f"| Given | {story_card.get('given', '')} |",
                f"| When | {story_card.get('when', '')} |",
                f"| Then | {story_card.get('then', '')} |",
                f"",
                f"**Acceptance criteria:**",
                f"",
            ]
            for criterion in story_card.get("acceptance", []):
                lines.append(f"- {criterion}")
            lines.append("")

        if gate_report:
            lines += [f"## Gate Report — {icon} {outcome}", f""]
            for cr in gate_report.get("criteria_results", []):
                r = cr.get("result", "?")
                r_icon = "✅" if r == "PASS" else ("⚠️" if r == "PARTIAL" else "❌")
                lines.append(f"- {r_icon} **{r}** — {cr.get('criterion', '')}")
                lines.append(f"  - *Evidence:* {cr.get('evidence', '')}")
            lines.append("")

            if gate_report.get("blockers"):
                lines += [f"**Blockers:**", ""]
                for b in gate_report["blockers"]:
                    lines.append(f"- ❌ {b}")
                lines.append("")

            if gate_report.get("deferred"):
                lines += [f"**Deferred (accepted):**", ""]
                for d in gate_report["deferred"]:
                    lines.append(f"- ⏭️ {d}")
                lines.append("")

            if outcome == "HOLD" and gate_report.get("hold_reason"):
                lines += [
                    f"**Hold reason for FORGE:**",
                    f"",
                    f"> {gate_report['hold_reason']}",
                    f"",
                ]

        def _render_agent_report(report: dict, decision_key: str, label: str) -> None:
            nonlocal lines
            decision = report.get(decision_key, "?")
            d_icon = "✅" if decision == "SHIP" else ("⚠️" if decision == "ADVISORY" else "❌")
            lines += [f"## {label} — {d_icon} {decision}", ""]
            for finding in report.get("findings", []):
                r = finding.get("result", "?")
                r_icon = "✅" if r == "PASS" else ("⚠️" if r == "ADVISORY" else "❌")
                lines.append(f"- {r_icon} **{r}** — {finding.get('check', '')}")
                lines.append(f"  - *Evidence:* {finding.get('evidence', '')}")
            lines.append("")
            if report.get("advisories"):
                lines += ["**Advisories (backlogged):**", ""]
                for a in report["advisories"]:
                    lines.append(f"- ⚠️ {a}")
                lines.append("")
            if report.get("blockers"):
                lines += ["**Blockers:**", ""]
                for b in report["blockers"]:
                    lines.append(f"- ❌ {b}")
                lines.append("")
            if decision in ("HOLD", "ADVISORY") and report.get("hold_reason"):
                lines += ["**Hold reason for FORGE:**", "", f"> {report['hold_reason']}", ""]

        if sentinel_report:
            _render_agent_report(sentinel_report, "sentinel_decision", "SENTINEL Report")
        if conduit_report:
            _render_agent_report(conduit_report, "conduit_decision", "CONDUIT Report")

    open_advisories = len(load_open_backlog())
    lines += [
        f"---",
        f"",
        f"| Metric | Value |",
        f"| --- | --- |",
        f"| Days complete | {stats['shipped']} / {total_days} |",
        f"| SHIP rate | {ship_rate} |",
        f"| Deferred items | {stats['deferred']} |",
        f"| Escalated holds | {stats['escalated']} |",
        f"| Open advisories | {open_advisories} |",
    ]

    # Item 4 deferred step 7: include PACE version update notice when available
    update_status = _load_update_status()
    if update_status and update_status.get("update_available"):
        new_ver = update_status.get("new_version", "?")
        cur_ver = update_status.get("current_version", "?")
        note = update_status.get("customization_note", "")
        lines += [
            f"",
            f"---",
            f"",
            f"## ⬆️ PACE Update Available",
            f"",
            f"**{new_ver}** is available (installed: {cur_ver}).",
            f"",
            f"> {note}",
            f"",
        ]

    markdown = "\n".join(lines)

    if ci is not None:
        ci.write_job_summary(markdown)
        return

    # Fallback: write directly to $GITHUB_STEP_SUMMARY (no adapter configured)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "w") as f:
            f.write(markdown)


def update_progress_md(current_day: int) -> None:
    """Rewrite PROGRESS.md with the current state of all completed days."""
    cfg = load_config()
    plan = _load_plan()
    plan_by_day = {d["day"]: d for d in plan["days"]}
    tz = ZoneInfo(cfg.reporter_timezone)
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M %Z")
    total_days = cfg.sprint_duration_days

    planner_report = _load_planner_report()
    estimates = _load_plan_estimates()
    has_costs = bool(planner_report)

    rows = []
    shipped_count = 0
    deferred_total = 0
    escalated_count = 0

    for day in range(1, total_days + 1):
        day_plan = plan_by_day.get(day, {})
        story, handoff, gate = _load_day_artifacts(day)

        est_cost = estimates.get(day, {}).get("predicted_cost_usd")
        actual_cost, run_count = _load_total_cost(day)

        if gate is None and day > current_day:
            rows.append((day, day_plan.get("target", "")[:60], "PENDING", "", est_cost, None, 0))
            continue

        if gate is None and day <= current_day:
            rows.append((day, day_plan.get("target", "")[:60], "IN PROGRESS", "", est_cost, actual_cost, run_count))
            continue

        decision = gate.get("gate_decision", "?")
        deferred = gate.get("deferred", [])
        deferred_total += len(deferred)

        escalation_file = PACE_DIR / f"day-{day}" / "escalated"
        if escalation_file.exists():
            escalated_count += 1

        if decision == "SHIP":
            shipped_count += 1

        notes = "; ".join(deferred) if deferred else ""
        rows.append((day, day_plan.get("target", "")[:60], decision, notes[:80], est_cost, actual_cost, run_count))

    ship_rate = f"{(shipped_count / current_day * 100):.0f}%" if current_day > 0 else "0%"
    open_advisories = len(load_open_backlog())

    lines = [
        f"# {cfg.product_name} — PACE Sprint Progress",
        "",
        f"**Started:** {plan.get('start_date', 'TBD')}  ",
        f"**Last updated:** {now}  ",
        f"**Target:** {total_days}-day sprint",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Days complete | {shipped_count} / {total_days} |",
        f"| SHIP rate | {ship_rate} |",
        f"| Deferred items | {deferred_total} |",
        f"| Escalated holds | {escalated_count} |",
        f"| Open advisories | {open_advisories} |",
        "",
        "## Day Log",
        "",
    ]

    if has_costs:
        lines += [
            "| Day | Story | Decision | Est. Cost | Actual Cost | Notes |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        # Day 0 planning row
        planning_cost = planner_report.get("planning_cost_usd", 0.0)
        planning_cost_str = f"${planning_cost:.4f}" if planning_cost else "—"
        lines.append(f"| 0 | Sprint planning | 📋 PLAN | — | {planning_cost_str} | Cost estimation |")
    else:
        lines += [
            "| Day | Story | Decision | Notes |",
            "| --- | --- | --- | --- |",
        ]

    for day, target, decision, notes, est_cost, actual_cost, run_count in rows:
        icon = RESULT_ICON.get(decision, "⏳")
        if has_costs:
            est_str = f"${est_cost:.2f}" if est_cost is not None else "—"
            if actual_cost is not None:
                actual_str = f"${actual_cost:.2f}"
                if run_count > 1:
                    actual_str += f" ({run_count}×)"
            else:
                actual_str = "—"
            lines.append(f"| {day} | {target} | {icon} {decision} | {est_str} | {actual_str} | {notes} |")
        else:
            lines.append(f"| {day} | {target} | {icon} {decision} | {notes} |")

    lines += [
        "",
        "---",
        "",
        "## Weekly Breakdown",
        "",
    ]

    # Group by week field from plan
    weeks_seen = sorted({plan_by_day.get(r[0], {}).get("week", 0) for r in rows if plan_by_day.get(r[0], {}).get("week")})
    for week in weeks_seen:
        week_days = [r for r in rows if plan_by_day.get(r[0], {}).get("week") == week]
        if not week_days:
            continue
        week_shipped = sum(1 for r in week_days if r[2] == "SHIP")
        week_total = len([r for r in week_days if r[2] not in ("PENDING",)])
        week_label = plan_by_day.get(week_days[0][0], {}).get("week_label", f"Week {week}")
        lines.append(f"### Week {week}" + (f" — {week_label}" if week_label != f"Week {week}" else ""))
        lines.append("")
        if week_total > 0:
            lines.append(f"**{week_shipped}/{week_total} days shipped**")
            lines.append("")
        for day, target, decision, notes, est_cost, actual_cost, run_count in week_days:
            icon = RESULT_ICON.get(decision, "⏳")
            lines.append(f"- Day {day}: {icon} {target}")
        lines.append("")

    if has_costs:
        total_estimated = planner_report.get("total_estimated_usd", 0.0)
        planning_cost = planner_report.get("planning_cost_usd", 0.0)
        # Total across all runs (including retries) from attempts.yaml when available
        total_with_retries = sum((_load_total_cost(d)[0] or 0.0) for d in range(1, total_days + 1))
        # Successful pipeline cost only (cycle.md / handoff.md)
        total_successful = sum(_load_cycle_cost(d) or 0.0 for d in range(1, total_days + 1))
        wasted = round(total_with_retries - total_successful, 4)
        forge_only_total = sum(_load_forge_cost(d) or 0.0 for d in range(1, total_days + 1))
        variance = total_successful - total_estimated
        variance_str = (f"+${variance:.2f}" if variance >= 0 else f"-${abs(variance):.2f}")
        variance_pct = f" ({variance / total_estimated * 100:+.0f}%)" if total_estimated > 0 else ""
        lines += [
            "---",
            "",
            "## Cost Summary",
            "",
            "| Metric | Value |",
            "| --- | --- |",
            f"| Total estimated (Days 1–{total_days}) | ${total_estimated:.2f} |",
            f"| Total actual (successful runs) | ${total_successful:.2f} |",
            f"| Total actual (incl. retries) | ${total_with_retries:.2f} |",
            f"| Wasted on retries | ${wasted:.2f} |",
            f"| Total actual (FORGE only) | ${forge_only_total:.2f} |",
            f"| Variance (successful vs estimated) | {variance_str}{variance_pct} |",
            f"| Day 0 planning cost | ${planning_cost:.4f} |",
            "",
        ]

    PROGRESS_FILE.write_text("\n".join(lines))
