"""System data cleaner - Junk only. All deletion goes through core.deleter."""
from core.deleter import DeleteReport, safe_delete
from scanner.system_data import ScanResult, scan_all


def clean_files(scan_result: ScanResult, dry_run: bool = False) -> DeleteReport:
    """Trash everything a Junk scan found. Safety checks live in safe_delete."""
    return safe_delete(scan_result.files, scan_result.category, dry_run=dry_run)


def clean_system_data(dry_run: bool = False) -> dict[str, DeleteReport]:
    """Scan and clean all Junk categories. Returns reports keyed by category."""
    return {
        result.category: clean_files(result, dry_run=dry_run)
        for result in scan_all()
    }
