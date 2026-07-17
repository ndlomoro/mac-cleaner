"""Privacy cleaner. Trash-able categories go through core.deleter; recents-clear
is an Irreversible Action (in-place rewrite) gated by the UI."""
from pathlib import Path

from core.deleter import DeleteReport, safe_delete
from scanner.privacy import scan_browser_data, scan_recently_used, scan_tracking_data
from utils.logger import log_cleaning_action


def clean_browser_data(dry_run: bool = False) -> DeleteReport:
    """Trash browser caches only (history is scanned for display, never cleaned here)."""
    items = [i for i in scan_browser_data() if i["type"] == "caches"]
    return safe_delete(items, "browser_cache", dry_run=dry_run)


def clean_tracking_data(dry_run: bool = False) -> DeleteReport:
    items = [i for i in scan_tracking_data()
             if "Preferences/ByHost" not in i["path"]]
    return safe_delete(items, "tracking_data", dry_run=dry_run)


def clean_privacy(dry_run: bool = False) -> dict[str, DeleteReport]:
    """Trash-able privacy categories. Recents is NOT included - it is an
    Irreversible Action the UI must gate and invoke separately."""
    return {
        "browser_cache": clean_browser_data(dry_run=dry_run),
        "tracking_data": clean_tracking_data(dry_run=dry_run),
    }


def clear_recently_used(dry_run: bool = False) -> dict:
    """Irreversible Action (registry: 'recents'): rewrites files in place."""
    stats = {"cleared": 0, "failed": 0}
    for item in scan_recently_used():
        path = Path(item["path"])
        try:
            if dry_run:
                stats["cleared"] += 1
                log_cleaning_action("Would Clear", str(path), dry_run=True)
                continue
            if path.is_file():
                path.write_text("")
                log_cleaning_action("Cleared", str(path))
            stats["cleared"] += 1
        except (OSError, PermissionError) as e:
            stats["failed"] += 1
            log_cleaning_action("Failed to Clear", f"{path} ({e})")
    return stats
