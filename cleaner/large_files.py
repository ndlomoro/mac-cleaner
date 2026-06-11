"""Large file cleaner - removes selected large files."""
from pathlib import Path
from send2trash import send2trash

from scanner.large_files import find_large_files
from utils.helpers import is_safe_to_delete
from utils.logger import log_cleaning_action


def clean_large_files(selected_paths: list[str], dry_run: bool = False) -> dict:
    """Clean specific large files by path. Returns cleanup stats."""
    stats = {"deleted": 0, "failed": 0, "freed_bytes": 0, "errors": []}

    for file_path in selected_paths:
        path = Path(file_path)
        if not is_safe_to_delete(path):
            stats["failed"] += 1
            stats["errors"].append(f"{path}: protected path")
            continue

        try:
            size = path.stat().st_size
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
