"""App remnants cleaner - removes leftover files from uninstalled apps."""
from pathlib import Path
from send2trash import send2trash

from scanner.app_remnants import find_leftovers
from utils.helpers import is_safe_to_delete
from utils.logger import log_cleaning_action


def clean_leftovers(app_name: str, dry_run: bool = False) -> dict:
    """Clean leftover files for a specific app."""
    leftovers = find_leftovers(app_name)
    stats = {"deleted": 0, "failed": 0, "freed_bytes": 0, "errors": []}

    for item in leftovers:
        path = Path(item["path"])
        if not is_safe_to_delete(path):
            continue

        try:
            size = item["size"]
            if dry_run:
                stats["deleted"] += 1
                stats["freed_bytes"] += size
                log_cleaning_action("Would Trash", str(path), dry_run=True)
                continue

            if path.exists():
                send2trash(path)
                log_cleaning_action("Trashed", str(path), dry_run=False)

            stats["deleted"] += 1
            stats["freed_bytes"] += size
        except Exception as e:
            stats["failed"] += 1
            stats["errors"].append(f"{path}: {e}")
            log_cleaning_action("Failed to Trash", f"{path} ({e})", dry_run=dry_run)

    return stats


def uninstall_app(app_name: str, dry_run: bool = False) -> dict:
    """Full uninstall: remove .app bundle + all leftovers."""
    import glob

    stats = {"app_removed": False, "leftovers": {}}

    # Find and remove the .app bundle
    app_paths = glob.glob(f"/Applications/{app_name}.app")
    for app_path in app_paths:
        path = Path(app_path)
        try:
            if dry_run:
                stats["app_removed"] = True
                log_cleaning_action("Would Trash App", str(path), dry_run=True)
                continue
            if path.exists():
                send2trash(path)
                log_cleaning_action("Trashed App", str(path), dry_run=False)
            stats["app_removed"] = True
        except Exception as e:
            log_cleaning_action("Failed to Trash App", f"{path} ({e})", dry_run=dry_run)

    # Clean leftovers
    stats["leftovers"] = clean_leftovers(app_name, dry_run=dry_run)

    return stats
