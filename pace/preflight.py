"""PACE Preflight — ensures context documents exist before the daily cycle runs.

Called once per orchestrator run. Instant no-op if all 4 docs are present.
Triggers SCRIBE to generate missing docs, then commits them.

Also runs the auto-update check (Item 4 — Auto-Update Mechanism):
  - check_for_update(): query GitHub releases API (cached 23h)
  - detect_customizations(): git diff against installed tag
  - emit WARNING if update available but customizations block it
  - apply_update() if no customizations and auto_update=true

To force a regeneration of any document: delete it from .pace/context/ and re-run.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

REPO_ROOT = Path(__file__).parent.parent
CONTEXT_DIR = REPO_ROOT / ".pace" / "context"

REQUIRED_DOCS = ["product.md", "engineering.md", "security.md", "devops.md"]


def _missing_docs() -> list[str]:
    return [doc for doc in REQUIRED_DOCS if not (CONTEXT_DIR / doc).exists()]


def _run_update_check() -> None:
    """Run the auto-update check. Non-fatal — errors are logged and skipped."""
    try:
        from config import load_config
        from updater import check_and_warn
        cfg = load_config()
        check_and_warn(
            auto_update=cfg.updates.auto_update,
            suppress_warning=cfg.updates.suppress_warning,
            channel=cfg.updates.channel,
        )
    except Exception as exc:
        print(f"[PACE] Update check skipped: {exc}")


def run_preflight(day: int) -> None:
    """Verify context documents are present. Run SCRIBE if any are missing.

    Also runs the auto-update check at the start of every pipeline run.
    """
    # Auto-update check (Item 4) — runs before SCRIBE to surface version info early
    _run_update_check()

    missing = _missing_docs()

    if not missing:
        print(f"[PACE] Preflight: context documents present — proceeding.")
        return

    print(f"[PACE] Preflight: missing {missing}. Running SCRIBE to generate context documents...")

    from agents.scribe import run_scribe
    try:
        run_scribe()
    except Exception as exc:
        raise RuntimeError(
            f"SCRIBE failed to generate context documents: {exc}\n"
            "Fix the underlying issue or manually create the missing files in .pace/context/ and retry."
        ) from exc

    still_missing = _missing_docs()
    if still_missing:
        raise RuntimeError(
            f"SCRIBE completed but context docs still missing: {still_missing}\n"
            "Check SCRIBE output above and manually create the missing files."
        )

    # Commit the generated docs
    result = subprocess.run(
        f'git add "{CONTEXT_DIR}" && '
        f'git commit -m "Day {day}: SCRIBE — generate context documents" && '
        f'git push origin HEAD',
        shell=True,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        # Non-fatal: docs are written, commit failure shouldn't block the day
        print(f"[PACE] Warning: could not commit context docs: {result.stderr.strip()}")

    print(f"[PACE] Preflight: all context documents ready.")
