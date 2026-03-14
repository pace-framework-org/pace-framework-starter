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

import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

REPO_ROOT = Path(__file__).parent.parent
CONTEXT_DIR = REPO_ROOT / ".pace" / "context"
LOCK_FILE = REPO_ROOT / ".pace" / "pipeline.lock"

# A lock older than this is considered stale (previous run crashed without cleanup).
_LOCK_MAX_AGE_SECONDS = 4 * 3600  # 4 hours

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


def acquire_pipeline_lock() -> None:
    """Write .pace/pipeline.lock with current PID and timestamp.

    Raises RuntimeError if a non-stale lock already exists (concurrent run).
    A stale lock (age > 4 hours) is removed and replaced.
    """
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    if LOCK_FILE.exists():
        try:
            age = time.time() - LOCK_FILE.stat().st_mtime
            if age < _LOCK_MAX_AGE_SECONDS:
                content = LOCK_FILE.read_text().strip()
                # Fire pipeline_lock_timeout alert (best-effort — must not block the error)
                try:
                    from config import load_config
                    from alert_engine import AlertEngine
                    AlertEngine(load_config()).fire(
                        "pipeline_lock_timeout",
                        {"lock_file": str(LOCK_FILE), "elapsed_minutes": round(age / 60, 1)},
                    )
                except Exception:
                    pass
                raise RuntimeError(
                    f"Pipeline lock is held by another run (age: {age/60:.1f}m).\n"
                    f"  Lock file: {LOCK_FILE}\n"
                    f"  Content: {content}\n"
                    "If this is stale, delete the lock file and retry."
                )
            else:
                print(
                    f"[PACE] Stale pipeline lock found (age: {age/3600:.1f}h) — removing and continuing."
                )
                LOCK_FILE.unlink(missing_ok=True)
        except (OSError, RuntimeError):
            raise

    LOCK_FILE.write_text(f"pid={os.getpid()}\nstarted={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n")
    print(f"[PACE] Pipeline lock acquired (PID {os.getpid()}).")


def release_pipeline_lock() -> None:
    """Remove .pace/pipeline.lock. No-op if it does not exist."""
    if LOCK_FILE.exists():
        LOCK_FILE.unlink(missing_ok=True)
        print("[PACE] Pipeline lock released.")


def run_preflight(day: int) -> None:
    """Verify context documents are present. Run SCRIBE if any are missing.

    Also runs the auto-update check (Item 4) and acquires the pipeline lock
    (Item 8) to prevent concurrent runs from corrupting .pace/ state files.
    """
    # Acquire the pipeline lock before any work (Item 8)
    acquire_pipeline_lock()

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
