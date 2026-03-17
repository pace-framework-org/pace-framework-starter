"""Migration: retroactively archive unversioned context files as *.pre-v3.md.

Any `.pace/context/*.md` file that has no matching entry in
`context.manifest.yaml` (or where no manifest exists at all) is treated as
pre-v3 and renamed to `<stem>.pre-v3.md` so the versioning system can take
over cleanly.

Usage:
    python pace/migrations/v3_context_versioning.py
    python pace/migrations/v3_context_versioning.py --context-dir /path/to/.pace/context
    python pace/migrations/v3_context_versioning.py --dry-run   # preview without renaming

Exit codes:
    0 — migration applied (or nothing to do)
    1 — error reading the context directory
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DEFAULT_CONTEXT = Path(__file__).parent.parent.parent / ".pace" / "context"
_KNOWN_DOCS = {"product.md", "engineering.md", "security.md", "devops.md"}
_ARCHIVE_SUFFIX = "pre-v3"


def migrate(context_dir: Path, dry_run: bool = False) -> int:
    """Archive unversioned context docs under *context_dir*.

    Returns 0 on success, 1 on error.
    """
    if not context_dir.exists():
        print(f"[migrate] {context_dir}: directory does not exist — nothing to do.")
        return 0

    # Determine which files are already tracked by the manifest (if any)
    manifest_path = context_dir / "context.manifest.yaml"
    tracked: set[str] = set()
    if manifest_path.exists():
        try:
            import yaml
            raw = yaml.safe_load(manifest_path.read_text()) or {}
            tracked = set(raw.get("files", []))
        except Exception as exc:  # noqa: BLE001
            print(f"[migrate] Warning: could not read manifest: {exc} — treating all files as unversioned.")

    to_archive = [
        f for f in context_dir.iterdir()
        if f.suffix == ".md" and f.name in _KNOWN_DOCS and f.name not in tracked
    ]

    if not to_archive:
        print(f"[migrate] {context_dir}: all known docs are already tracked or absent — nothing to do.")
        return 0

    for src in sorted(to_archive):
        stem = src.stem
        dest = context_dir / f"{stem}.{_ARCHIVE_SUFFIX}.md"
        if dry_run:
            print(f"[migrate] DRY RUN: would rename {src.name} → {dest.name}")
        else:
            try:
                src.rename(dest)
                print(f"[migrate] Archived {src.name} → {dest.name}")
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: could not rename {src.name}: {exc}", file=sys.stderr)
                return 1

    if not dry_run:
        print(
            f"[migrate] {len(to_archive)} file(s) archived. "
            "SCRIBE will regenerate fresh context on next run."
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--context-dir", type=Path, default=_DEFAULT_CONTEXT,
        help="Path to .pace/context/ directory",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without renaming")
    args = parser.parse_args()
    sys.exit(migrate(args.context_dir, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
