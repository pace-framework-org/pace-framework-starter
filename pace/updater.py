"""PACE Auto-Update Mechanism (ROADMAP Item 4).

Provides three functions used by preflight.py at pipeline startup:

    check_for_update()       — query GitHub releases API; cache result 23h
    detect_customizations()  — git diff against installed tag to find modified PACE files
    apply_update()           — pull new tag and reinstall deps (only when no customizations)

Configuration (pace.config.yaml):
    updates:
      auto_update: true         # false = disable version checking entirely
      suppress_warning: false   # true = silence the customization WARNING
      channel: stable           # stable | beta

Environment:
    PACE_UPDATE_REPO  — override the upstream repo (default: pace-framework-org/pace-framework-starter)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

_REPO_ROOT = Path(__file__).parent.parent
_PACE_DIR = _REPO_ROOT / ".pace"
_UPDATE_CACHE = _PACE_DIR / "update_check.json"
_LOCK_FILE = _PACE_DIR / "pipeline.lock"

_UPSTREAM_REPO = os.environ.get(
    "PACE_UPDATE_REPO", "pace-framework-org/pace-framework-starter"
)
_CACHE_TTL_SECONDS = 23 * 3600  # 23 hours

# Tutorial URL referenced in WARNING messages
_UPGRADE_TUTORIAL = "https://pace-framework.org/tutorials/existing-project/"

# Path to write update status for the reporter
_UPDATE_STATUS_FILE = _PACE_DIR / "update_status.yaml"


def _current_version() -> str:
    """Return the installed PACE_VERSION constant from config.py."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from config import PACE_VERSION
        return PACE_VERSION
    except Exception:
        return "0.0.0"


def _fetch_latest_release(channel: str = "stable") -> dict | None:
    """Query the GitHub releases API and return the latest release dict.

    channel "stable" → latest non-prerelease tag.
    channel "beta"   → latest tag including pre-releases.
    Returns None on any error.
    """
    if not _REQUESTS_AVAILABLE:
        return None
    try:
        if channel == "beta":
            url = f"https://api.github.com/repos/{_UPSTREAM_REPO}/releases"
            resp = _requests.get(url, timeout=10,
                                 headers={"Accept": "application/vnd.github+json"})
            resp.raise_for_status()
            releases = resp.json()
            return releases[0] if releases else None
        else:
            url = f"https://api.github.com/repos/{_UPSTREAM_REPO}/releases/latest"
            resp = _requests.get(url, timeout=10,
                                 headers={"Accept": "application/vnd.github+json"})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        print(f"[PACE Updater] Could not fetch release info: {e}")
        return None


def _read_cache() -> dict | None:
    """Return cached update_check data if it is not stale, else None."""
    if not _UPDATE_CACHE.exists():
        return None
    try:
        data = json.loads(_UPDATE_CACHE.read_text())
        cached_at = data.get("cached_at", 0)
        if time.time() - cached_at < _CACHE_TTL_SECONDS:
            return data
    except Exception as e:
        # Treat any cache read/parse error as a cache miss — non-fatal.
        print(f"[PACE Updater] Ignoring stale or corrupted cache: {e}")
    return None


def _write_cache(data: dict) -> None:
    """Write update_check data with a timestamp to the cache file."""
    _PACE_DIR.mkdir(parents=True, exist_ok=True)
    data["cached_at"] = time.time()
    try:
        _UPDATE_CACHE.write_text(json.dumps(data, indent=2))
    except OSError:
        pass  # Non-fatal — cache is best-effort


def check_for_update(channel: str = "stable") -> dict:
    """Return a dict describing the update status.

    Keys:
        current_version  — installed PACE version
        latest_version   — latest published version (or same as current on error)
        update_available — True if latest > current
        from_cache       — True if result came from the 23h cache
    """
    current = _current_version()

    cached = _read_cache()
    if cached:
        cached["from_cache"] = True
        cached["current_version"] = current
        cached["update_available"] = _is_newer(cached.get("latest_version", current), current)
        return cached

    release = _fetch_latest_release(channel)
    if release is None:
        return {
            "current_version": current,
            "latest_version": current,
            "update_available": False,
            "from_cache": False,
        }

    latest = release.get("tag_name", current).lstrip("v")
    result = {
        "current_version": current,
        "latest_version": latest,
        "update_available": _is_newer(latest, current),
        "from_cache": False,
    }
    _write_cache(result)
    return result


def _is_newer(latest: str, current: str) -> bool:
    """Return True if latest semver > current semver."""
    try:
        return tuple(int(x) for x in latest.split(".")) > tuple(int(x) for x in current.split("."))
    except (ValueError, AttributeError):
        return False


def detect_customizations(installed_tag: str | None = None) -> list[str]:
    """Return a list of PACE core files that differ from the installed tag.

    Runs `git diff <tag> -- pace/` in the repo root. An empty list means no
    customizations — auto-update is safe. A non-empty list blocks auto-update.

    installed_tag: e.g. "v1.2.0". Defaults to "v{current_version}".
    """
    if installed_tag is None:
        installed_tag = f"v{_current_version()}"

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", installed_tag, "--", "pace/"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            timeout=15,
        )
        if result.returncode != 0:
            # Tag may not exist locally — treat as no customizations detectable
            return []
        modified = [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip()
        ]
        return modified
    except Exception as e:
        print(f"[PACE Updater] detect_customizations error: {e}")
        return []


def apply_update(new_tag: str) -> bool:
    """Fetch and check out new_tag; reinstall requirements. Returns True on success.

    Only call this after detect_customizations() returns an empty list.
    Aborts immediately if the pipeline lock exists (another run is active).
    """
    if _LOCK_FILE.exists():
        print("[PACE Updater] Pipeline lock active — skipping update to avoid race condition.")
        return False

    print(f"[PACE Updater] Applying update to {new_tag}...")
    try:
        subprocess.run(
            ["git", "fetch", "--tags", "origin"],
            check=True, capture_output=True, cwd=str(_REPO_ROOT), timeout=60,
        )
        subprocess.run(
            ["git", "checkout", new_tag, "--", "pace/"],
            check=True, capture_output=True, cwd=str(_REPO_ROOT), timeout=30,
        )
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r",
             str(_REPO_ROOT / "pace" / "requirements.txt"), "-q"],
            check=True, capture_output=True, timeout=120,
        )
        # Update cache to reflect the new version
        _write_cache({
            "current_version": new_tag.lstrip("v"),
            "latest_version": new_tag.lstrip("v"),
            "update_available": False,
        })
        print(f"[PACE Updater] Successfully updated to {new_tag}.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[PACE Updater] Update failed: {e.stderr.decode(errors='replace')[:200] if e.stderr else e}")
        return False
    except Exception as e:
        print(f"[PACE Updater] Unexpected error during update: {e}")
        return False


def _write_update_status(new_tag: str, current: str, customizations: list[str]) -> None:
    """Persist update availability to .pace/update_status.yaml for reporter.py."""
    _PACE_DIR.mkdir(parents=True, exist_ok=True)
    import json as _json
    note = (
        "Customized files prevent auto-update: " + ", ".join(customizations[:3])
        + (" ..." if len(customizations) > 3 else "")
        if customizations
        else "Auto-update is disabled in config."
    )
    data = {
        "update_available": True,
        "new_version": new_tag,
        "current_version": f"v{current}",
        "customization_note": note,
    }
    try:
        _UPDATE_STATUS_FILE.write_text(_json.dumps(data, indent=2))
    except OSError:
        pass


def _clear_update_status() -> None:
    """Remove .pace/update_status.yaml when no update is available."""
    try:
        _UPDATE_STATUS_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _fire_update_available_event(new_tag: str, current: str, customizations: list[str]) -> None:
    """Fire the update_available AlertEngine event (best-effort, non-fatal)."""
    try:
        from config import load_config
        from alert_engine import AlertEngine
        note = (
            "Customized files prevent auto-update: " + ", ".join(customizations[:3])
            + (" ..." if len(customizations) > 3 else "")
            if customizations
            else "Auto-update is disabled in config."
        )
        AlertEngine(load_config()).fire("update_available", {
            "new_version": new_tag,
            "current_version": f"v{current}",
            "customization_note": note,
        })
    except Exception:
        pass  # Non-fatal — alert dispatch must never block the pipeline


def check_and_warn(
    auto_update: bool = True,
    suppress_warning: bool = False,
    channel: str = "stable",
) -> None:
    """Run the update check and either apply the update or emit a WARNING.

    Called by preflight.py at pipeline startup. This is the primary entry point
    for the auto-update mechanism.

    Behaviour:
      - update_available=False → silent (no-op)
      - update_available=True, no customizations → apply_update()
      - update_available=True, customizations found → emit WARNING (unless suppressed)
      - auto_update=False → version check only; never applies update; still warns
    """
    if not auto_update and suppress_warning:
        return  # Both disabled — nothing to do

    info = check_for_update(channel=channel)
    if not info.get("update_available"):
        return

    current = info["current_version"]
    latest = info["latest_version"]
    new_tag = f"v{latest}"

    customizations = detect_customizations()

    if auto_update and not customizations:
        applied = apply_update(new_tag)
        if applied:
            _clear_update_status()
            print(f"[PACE] Auto-updated to {new_tag}. Continuing pipeline with new version.")
            return

    # Could not auto-update — persist status, fire event, and emit WARNING if not suppressed
    _write_update_status(new_tag, current, customizations)
    _fire_update_available_event(new_tag, current, customizations)

    if not suppress_warning:
        if customizations:
            files_list = "\n".join(f"    - {f}" for f in customizations[:10])
            extra = f" (and {len(customizations) - 10} more)" if len(customizations) > 10 else ""
            print(
                f"\n⚠  PACE {new_tag} is available (installed: v{current}).\n"
                f"   Auto-update skipped — customized PACE files detected:\n"
                f"{files_list}{extra}\n"
                f"   Run the manual upgrade tutorial to merge new version features\n"
                f"   while preserving your customizations. See:\n"
                f"   {_UPGRADE_TUTORIAL}\n"
                f"   (Suppress this warning with updates.suppress_warning: true)\n"
            )
        else:
            print(
                f"\n⚠  PACE {new_tag} is available (installed: v{current}).\n"
                f"   Auto-update is disabled (updates.auto_update: false).\n"
                f"   Set auto_update: true or update manually.\n"
            )
