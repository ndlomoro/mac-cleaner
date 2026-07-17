"""App uninstaller - removes .app bundle + leftovers via core.deleter."""
from pathlib import Path

from core.deleter import DeleteReport, safe_delete
from scanner.app_remnants import find_leftovers
from utils.helpers import get_dir_size

APPLICATIONS_DIR = Path("/Applications")


def clean_leftovers(app_name: str, dry_run: bool = False) -> DeleteReport:
    return safe_delete(find_leftovers(app_name), "app_leftovers", dry_run=dry_run)


def uninstall_app(app_name: str, dry_run: bool = False) -> dict:
    """Trash the .app bundle and its leftovers. Returns {'app': DeleteReport,
    'leftovers': DeleteReport}."""
    bundle = APPLICATIONS_DIR / f"{app_name}.app"
    bundle_items = []
    if bundle.exists():
        bundle_items.append({"path": str(bundle), "size": get_dir_size(bundle)})

    return {
        "app": safe_delete(bundle_items, "app_bundle", dry_run=dry_run),
        "leftovers": clean_leftovers(app_name, dry_run=dry_run),
    }
