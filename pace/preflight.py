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


def _check_branch_protection() -> None:
    """Warn if the default GitHub branch lacks protection rules. Non-fatal."""
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        return  # Not GitHub or credentials missing — skip silently

    try:
        import urllib.request
        import json as _json

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        def _gh_get(url: str) -> dict | None:
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return _json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                return {"_status": e.code}
            except Exception:
                return None

        repo_data = _gh_get(f"https://api.github.com/repos/{repo}")
        if not repo_data or "_status" in repo_data:
            return
        default_branch = repo_data.get("default_branch", "main")

        protection = _gh_get(
            f"https://api.github.com/repos/{repo}/branches/{default_branch}/protection"
        )
        if protection and protection.get("_status") == 404:
            print(
                f"[PACE] WARNING: Branch '{default_branch}' has no protection rules. "
                "Consider enabling branch protection to prevent direct pushes."
            )
        elif protection and "_status" not in protection:
            print(f"[PACE] Branch '{default_branch}' is protected.")
    except Exception:
        pass  # Non-fatal — branch protection check must never block the pipeline


def _archive_context_for_release_change() -> None:
    """Archive existing context files when the active release has changed.

    Reads .pace/context/context.manifest.yaml; if the release recorded there
    differs from the current active release, renames each context file to
    <name>.<old-release>.md and deletes the original so SCRIBE generates fresh
    copies for the new release. Non-fatal on any error.
    """
    try:
        import yaml as _yaml
        from config import load_config

        cfg = load_config()
        active = cfg.active_release
        if not active:
            return  # No release configured — versioning not applicable

        manifest_path = CONTEXT_DIR / "context.manifest.yaml"
        if not manifest_path.exists():
            return  # No manifest yet — first run, nothing to archive

        raw = _yaml.safe_load(manifest_path.read_text()) or {}
        manifest_release = raw.get("release", "")
        if not manifest_release or manifest_release == active.name:
            return  # Same release — no archival needed

        print(
            f"[PACE] Release changed from '{manifest_release}' → '{active.name}'. "
            "Archiving context files for prior release..."
        )
        archived = []
        for doc in REQUIRED_DOCS:
            src = CONTEXT_DIR / doc
            if src.exists():
                stem = doc.replace(".md", "")
                dest = CONTEXT_DIR / f"{stem}.{manifest_release}.md"
                src.rename(dest)
                archived.append(dest.name)

        # Also archive the old manifest itself
        manifest_archive = CONTEXT_DIR / f"context.manifest.{manifest_release}.yaml"
        manifest_path.rename(manifest_archive)
        archived.append(manifest_archive.name)

        print(f"[PACE] Archived {len(archived)} context files: {archived}")

    except Exception as exc:
        # Non-fatal — archival failure must never block the pipeline
        print(f"[PACE] Warning: context archival skipped: {exc}")


def acquire_pipeline_lock() -> None:
    """Write .pace/pipeline.lock with current PID and timestamp.

    Raises RuntimeError if a non-stale lock already exists (concurrent run).
    A stale lock (age > 4 hours) is removed and replaced.
    """
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    if LOCK_FILE.exists():
        try:
            # Use the timestamp embedded in the file content (st_mtime is unreliable
            # after a git checkout, where the file's mtime is set to checkout time).
            content = LOCK_FILE.read_text().strip()
            age = _LOCK_MAX_AGE_SECONDS + 1  # default: treat as stale
            for line in content.splitlines():
                if line.startswith("started="):
                    try:
                        import datetime
                        started = datetime.datetime.strptime(
                            line[len("started="):], "%Y-%m-%dT%H:%M:%SZ"
                        ).replace(tzinfo=datetime.timezone.utc)
                        age = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()
                    except ValueError:
                        pass
                    break
            if age < _LOCK_MAX_AGE_SECONDS:
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

    # Branch protection check (Item 1 deferred step 6) — non-fatal advisory
    _check_branch_protection()

    # Context versioning (Item 12) — archive prior-release docs before SCRIBE runs
    _archive_context_for_release_change()

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
