"""Migration: v2.x release: → v3.0 releases: list.

Reads the legacy single ``release:`` key from pace.config.yaml and rewrites it
as a one-entry ``releases:`` list with ``status: active``. The original
``release:`` key is removed.

Usage:
    python pace/migrations/v3_multi_release.py
    python pace/migrations/v3_multi_release.py --config /path/to/pace.config.yaml
    python pace/migrations/v3_multi_release.py --dry-run   # preview without writing

Exit codes:
    0 — migration applied (or already migrated / not needed)
    1 — error reading or writing the config file
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

_DEFAULT_CONFIG = Path(__file__).parent.parent / "pace.config.yaml"


def migrate(config_path: Path, dry_run: bool = False) -> int:
    """Migrate *config_path* from legacy ``release:`` to ``releases:`` list.

    Returns 0 on success, 1 on error.
    """
    try:
        text = config_path.read_text()
        raw: dict = yaml.safe_load(text) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not read {config_path}: {exc}", file=sys.stderr)
        return 1

    if "releases" in raw:
        print(f"[migrate] {config_path}: already uses releases: list — nothing to do.")
        return 0

    release = raw.get("release")
    if not release or not release.get("name"):
        print(f"[migrate] {config_path}: no release: section found — nothing to do.")
        return 0

    # Build the new releases: entry
    new_entry = {
        "name": str(release["name"]),
        "release_days": int(release.get("release_days", 90)),
        "sprint_days": int(release.get("sprint_days", 7)),
        "status": "active",
    }
    if release.get("plan_file"):
        new_entry["plan_file"] = str(release["plan_file"])

    # Rebuild the dict: insert releases: right where release: was, then drop release:
    new_raw: dict = {}
    for key, value in raw.items():
        if key == "release":
            new_raw["releases"] = [new_entry]
        else:
            new_raw[key] = value

    new_text = yaml.dump(new_raw, default_flow_style=False, allow_unicode=True, sort_keys=False)

    if dry_run:
        print(f"[migrate] DRY RUN — would rewrite {config_path}:\n")
        print(new_text)
        return 0

    try:
        config_path.write_text(new_text)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not write {config_path}: {exc}", file=sys.stderr)
        return 1

    print(
        f"[migrate] {config_path}: migrated release: → releases: (1 entry, status: active). "
        "Commit the updated config before running PACE."
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG, help="Path to pace.config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()
    sys.exit(migrate(args.config, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
