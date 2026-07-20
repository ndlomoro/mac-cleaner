"""Large file cleaner - Reclaimable User Data, individually selected paths only.

Retained for the scanner/cleaner pairing convention (it pairs with
scanner/large_files.py). The Space Finder no longer routes large_files through
here - it deletes every category uniformly via core.deleter.trash_selection,
which owns the Keep-One Invariant - so this is currently exercised only by its
own tests.
"""
from pathlib import Path

from core.deleter import DeleteReport, safe_delete


def clean_large_files(selected_paths: list[str], dry_run: bool = False) -> DeleteReport:
    """Trash explicitly user-selected large files. Never called with scan output wholesale."""
    items = []
    for file_path in selected_paths:
        try:
            size = Path(file_path).stat().st_size
        except OSError:
            size = 0
        items.append({"path": file_path, "size": size})
    return safe_delete(items, "large_files", dry_run=dry_run, user_selected=True)
