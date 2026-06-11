"""Privacy cleaner - removes browser cache, tracking data, recents."""
from pathlib import Path
from send2trash import send2trash

from scanner.privacy import scan_browser_data, scan_tracking_data, scan_recently_used
from utils.helpers import is_safe_to_delete
from utils.logger import log_cleaning_action


def clean_browser_data(dry_run: bool = False) -> dict:
    """Clean browser cache and history data."""
    items = scan_browser_data()
    stats = {"deleted": 0, "failed": 0, "freed_bytes": 0, "errors": []}

    for item in items:
        path = Path(item["path"])
        if item["type"] == "caches" and is_safe_to_delete(path):
            try:
                if dry_run:
                    stats["deleted"] += 1
                    stats["freed_bytes"] += item["size"]
                    log_cleaning_action("Would Trash", str(path), dry_run=True)
                    continue
                if path.exists():
                    send2trash(path)
                    log_cleaning_action("Trashed", str(path), dry_run=False)
                stats["deleted"] += 1
                stats["freed_bytes"] += item["size"]
            except Exception as e:
                stats["failed"] += 1
                stats["errors"].append(f"{path}: {e}")
                log_cleaning_action("Failed to Trash", f"{path} ({e})", dry_run=dry_run)

    return stats


def clean_tracking_data(dry_run: bool = False) -> dict:
    """Clean tracking and diagnostic data."""
    items = scan_tracking_data()
    stats = {"deleted": 0, "failed": 0, "freed_bytes": 0, "errors": []}

    for item in items:
        path = Path(item["path"])
        if not is_safe_to_delete(path):
            continue
        if "Preferences/ByHost" in str(path):
            continue
        try:
            if dry_run:
                stats["deleted"] += 1
                stats["freed_bytes"] += item["size"]
                log_cleaning_action("Would Trash", str(path), dry_run=True)
                continue
            if path.exists():
                send2trash(path)
                log_cleaning_action("Trashed", str(path), dry_run=False)
            stats["deleted"] += 1
            stats["freed_bytes"] += item["size"]
        except Exception as e:
            stats["failed"] += 1
            stats["errors"].append(f"{path}: {e}")
            log_cleaning_action("Failed to Trash", f"{path} ({e})", dry_run=dry_run)

    return stats


def clear_recently_used(dry_run: bool = False) -> dict:
    """Clear recently used items list."""
    items = scan_recently_used()
    stats = {"cleared": 0, "failed": 0}

    for item in items:
        path = Path(item["path"])
        try:
            if dry_run:
                stats["cleared"] += 1
                log_cleaning_action("Would Clear", str(path), dry_run=True)
                continue
            if path.is_file():
                path.write_text("")
                log_cleaning_action("Cleared", str(path), dry_run=False)
            stats["cleared"] += 1
        except Exception as e:
            stats["failed"] += 1
            log_cleaning_action("Failed to Clear", f"{path} ({e})", dry_run=dry_run)

    return stats


def clean_privacy(dry_run: bool = False) -> dict:
    """Run full privacy cleanup."""
    return {
        "browser_cache": clean_browser_data(dry_run=dry_run),
        "tracking_data": clean_tracking_data(dry_run=dry_run),
        "recently_used": clear_recently_used(dry_run=dry_run),
    }
