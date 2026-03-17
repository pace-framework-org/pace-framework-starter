"""PACE Pacemap — ROADMAP versioning and CHANGELOG management (Item 17 + 18).

Provides:
    snapshot_roadmap(version, summary)        — archive current ROADMAP.md to
                                                .pacemap/versions/ROADMAP-v<N>.md
                                                and commit .pacemap/.
    update_changelog(version, added,          — insert a new versioned block into
                     changed, fixed)            CHANGELOG.md above ## [Unreleased].
    update_changelog_story_shipped(           — append a line to the ## [Unreleased]
        story_id, release, summary)             section of CHANGELOG.md.

All public functions are non-fatal on I/O errors — they print a warning and
return False so callers can continue without interruption.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
PACEMAP_DIR = REPO_ROOT / ".pacemap"
VERSIONS_DIR = PACEMAP_DIR / "versions"
ROADMAP_FILE = PACEMAP_DIR / "ROADMAP.md"
CHANGELOG_FILE = REPO_ROOT / "CHANGELOG.md"

# Header field that triggers a snapshot when its value changes.
_VERSION_HEADER_RE = re.compile(r"^\*\*Roadmap Version:\*\*\s+(.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def _read_roadmap_version(text: str) -> str | None:
    """Extract the Roadmap Version value from ROADMAP.md text."""
    m = _VERSION_HEADER_RE.search(text)
    if not m:
        return None
    # Take only the leading version token (e.g. "1.5" from "1.5 (revised ...)")
    return m.group(1).strip().split()[0]


def _git_commit_pacemap(message: str) -> bool:
    """Stage .pacemap/ and commit with *message*. Returns True on success."""
    try:
        subprocess.run(
            ["git", "add", str(PACEMAP_DIR)],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=REPO_ROOT,
            capture_output=True,
        )
        if result.returncode == 0:
            return True  # nothing to commit
        subprocess.run(
            ["git", "commit", "-m", message],
            check=True,
            cwd=REPO_ROOT,
            capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        print(f"[pacemap] git commit failed (non-fatal): {exc}")
        return False


# ---------------------------------------------------------------------------
# Public API — Item 17
# ---------------------------------------------------------------------------


def snapshot_roadmap(version: str, summary: str) -> bool:
    """Archive the current ROADMAP.md as .pacemap/versions/ROADMAP-v<version>.md.

    Creates an immutable snapshot of the roadmap at *version* and commits
    ``.pacemap/`` with a standardised message.  Safe to call even if the
    snapshot already exists (returns True without overwriting).

    Args:
        version: Version string, e.g. ``"1.5"`` or ``"2.0"``.
        summary: One-line description for the commit message.

    Returns:
        True on success, False if any step fails (non-fatal).
    """
    try:
        if not ROADMAP_FILE.exists():
            print(f"[pacemap] ROADMAP.md not found at {ROADMAP_FILE} — skipping snapshot.")
            return False

        VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
        snapshot_path = VERSIONS_DIR / f"ROADMAP-v{version}.md"

        if snapshot_path.exists():
            print(f"[pacemap] Snapshot {snapshot_path.name} already exists — skipping.")
            return True

        snapshot_path.write_text(ROADMAP_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"[pacemap] Snapshot written: {snapshot_path.relative_to(REPO_ROOT)}")

        commit_msg = f"[pacemap] ROADMAP v{version}: {summary}"
        return _git_commit_pacemap(commit_msg)

    except Exception as exc:
        print(f"[pacemap] snapshot_roadmap failed (non-fatal): {exc}")
        return False


def snapshot_roadmap_if_version_changed(previous_text: str, current_text: str) -> bool:
    """Compare roadmap version headers; snapshot previous if the version changed.

    Called by ``ci_generator.py`` after writing an updated ROADMAP.md.

    Args:
        previous_text: ROADMAP.md content *before* the update.
        current_text:  ROADMAP.md content *after* the update.

    Returns:
        True if no snapshot was needed or snapshot succeeded; False on error.
    """
    prev_ver = _read_roadmap_version(previous_text)
    curr_ver = _read_roadmap_version(current_text)

    if prev_ver is None or curr_ver is None or prev_ver == curr_ver:
        return True  # no version change — nothing to snapshot

    summary = f"snapshot before upgrade to v{curr_ver}"
    return snapshot_roadmap(prev_ver, summary)


# ---------------------------------------------------------------------------
# Public API — Item 18 (CHANGELOG helpers)
# ---------------------------------------------------------------------------

_UNRELEASED_HEADING = "## [Unreleased]"
# Pattern string for the Unreleased block (for documentation / future use).
_UNRELEASED_BLOCK_PATTERN = r"(## \[Unreleased\])(.*?)(?=\n## \[|\Z)"


def _today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def update_changelog(
    version: str,
    added: list[str] | None = None,
    changed: list[str] | None = None,
    fixed: list[str] | None = None,
) -> bool:
    """Insert a new versioned block into CHANGELOG.md.

    Moves the content of the current ``## [Unreleased]`` section into a new
    ``## [<version>] — <date>`` block and resets Unreleased to empty.

    Args:
        version: Release version string, e.g. ``"v3.0.0"``.
        added:   List of "Added" bullet strings (without leading ``- ``).
        changed: List of "Changed" bullet strings.
        fixed:   List of "Fixed" bullet strings.

    Returns:
        True on success, False on I/O error (non-fatal).
    """
    try:
        if not CHANGELOG_FILE.exists():
            print("[pacemap] CHANGELOG.md not found — skipping update_changelog.")
            return False

        text = CHANGELOG_FILE.read_text(encoding="utf-8")

        # Build the new versioned block from the provided lists
        sections: list[str] = []
        for heading, items in (("Added", added), ("Changed", changed), ("Fixed", fixed)):
            if items:
                sections.append(f"\n### {heading}\n\n" + "\n".join(f"- {i}" for i in items))

        versioned_block = f"## [{version}] — {_today_iso()}" + "".join(sections)

        # Replace Unreleased block: keep heading, clear content, prepend versioned block
        if _UNRELEASED_HEADING in text:
            # Insert versioned block right after the Unreleased heading line
            text = text.replace(
                _UNRELEASED_HEADING,
                f"{_UNRELEASED_HEADING}\n\n---\n\n{versioned_block}",
                1,
            )
        else:
            # No Unreleased section — prepend versioned block after the top-level heading
            lines = text.splitlines(keepends=True)
            insert_at = 1  # after the first line (# CHANGELOG)
            lines.insert(insert_at, f"\n{versioned_block}\n")
            text = "".join(lines)

        CHANGELOG_FILE.write_text(text, encoding="utf-8")
        print(f"[pacemap] CHANGELOG.md updated with release block [{version}].")
        return True

    except Exception as exc:
        print(f"[pacemap] update_changelog failed (non-fatal): {exc}")
        return False


def update_changelog_story_shipped(
    story_id: str, release: str, summary: str
) -> bool:
    """Append a story-shipped line to the ## [Unreleased] section.

    Called by ``orchestrator.py`` on SHIP.

    Args:
        story_id: Human-readable story identifier, e.g. ``"Day 3"``.
        release:  Release name, e.g. ``"v2.0"``.
        summary:  Short story summary (truncated to 80 chars).

    Returns:
        True on success, False on I/O error (non-fatal).
    """
    try:
        if not CHANGELOG_FILE.exists():
            return True  # CHANGELOG.md optional — silently skip

        text = CHANGELOG_FILE.read_text(encoding="utf-8")
        line = f"- [{release}] {story_id}: {summary[:80]}"

        if _UNRELEASED_HEADING in text:
            text = text.replace(
                _UNRELEASED_HEADING,
                f"{_UNRELEASED_HEADING}\n{line}",
                1,
            )
        else:
            text = f"{_UNRELEASED_HEADING}\n{line}\n\n" + text

        CHANGELOG_FILE.write_text(text, encoding="utf-8")
        return True

    except Exception as exc:
        print(f"[pacemap] update_changelog_story_shipped failed (non-fatal): {exc}")
        return False
