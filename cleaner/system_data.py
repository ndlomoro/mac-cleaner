"""System data cleaner - safely removes caches, logs, temp files."""
from pathlib import Path
from send2trash import send2trash

from scanner.system_data import scan_all, ScanResult
from utils.helpers import is_safe_to_delete
from utils.logger import log_cleaning_action


def clean_files(scan_result: ScanResult, dry_run: bool = False) -> dict:
    """Clean files from a scan result. Returns cleanup stats."""
    stats = {"deleted": 0, "failed": 0, "freed_bytes": 0, "errors": []}

    for file_info in scan_result.files:
        path = Path(file_info["path"])
        if not is_safe_to_delete(path):
            continue

        try:
            if dry_run:
                stats["deleted"] += 1
                stats["freed_bytes"] += file_info["size"]
                log_cleaning_action("Would Trash", str(path), dry_run=True)
                continue

            if path.exists():
                send2trash(path)
                log_cleaning_action("Trashed", str(path), dry_run=False)

            stats["deleted"] += 1
            stats["freed_bytes"] += file_info["size"]
        except Exception as e:
            stats["failed"] += 1
            stats["errors"].append(f"{path}: {e}")
            log_cleaning_action("Failed to Trash", f"{path} ({e})", dry_run=dry_run)

    return stats


def clean_system_data(dry_run: bool = False) -> dict:
    """Run full system data scan and clean. Returns per-category results."""
    results = scan_all()
    cleanup = {}

    for result in results:
        stats = clean_files(result, dry_run=dry_run)
        cleanup[result.name] = {
            "category": result.category,
            "files_scanned": result.file_count,
            "total_size": result.total_size,
            **stats,
        }

    return cleanup
