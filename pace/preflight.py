"""PACE Preflight — ensures context documents exist before the daily cycle runs.

Called once per orchestrator run. Instant no-op if all 4 docs are present.
Triggers SCRIBE to generate missing docs, then commits them.

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


def run_preflight(day: int) -> None:
    """Verify context documents are present. Run SCRIBE if any are missing."""
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
