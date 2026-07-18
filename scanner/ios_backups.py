"""iOS backup scanner - metadata-rich rows from read-only Info.plist parsing.

Never opens Manifest.plist/Manifest.db (encrypted-backup internals).
"""
import plistlib
from datetime import datetime
from pathlib import Path

from scanner.system_data import ScanResult
from utils.helpers import HOME, file_age_days, get_dir_size

BACKUP_ROOT = HOME / "Library" / "Application Support" / "MobileSync" / "Backup"


def _read_info(backup_dir: Path) -> dict:
    info = backup_dir / "Info.plist"
    try:
        with open(info, "rb") as f:
            data = plistlib.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        # Fully-isolated boundary: any read/parse failure degrades to {}
        # rather than aborting the whole scan. Deliberately broad because
        # a truncated XML-format Info.plist raises xml.parsers.expat.ExpatError
        # (via plistlib's XML parser), not just OSError/InvalidFileException/
        # ValueError - and no single backup's bad metadata may drop every
        # other backup from the list.
        return {}


def _backup_age_days(info: dict, backup_dir: Path) -> int:
    last = info.get("Last Backup Date")
    if isinstance(last, datetime):
        # datetime.now()/delta.days is UTC-naive-imprecise at the day
        # boundary (local calendar day vs. exact 24h elapsed); acceptable
        # here since age_days only drives a coarse staleness signal.
        delta = datetime.now(tz=last.tzinfo) - last
        return max(0, int(delta.days))
    return int(file_age_days(backup_dir))


def scan_ios_backups() -> ScanResult:
    result = ScanResult("ios_backups", "iOS Backups")
    if not BACKUP_ROOT.exists():
        return result
    try:
        for item in BACKUP_ROOT.iterdir():
            if not item.is_dir():
                continue
            info = _read_info(item)
            name = info.get("Device Name") or info.get("Display Name")
            result.add_file(str(item), get_dir_size(item),
                            _backup_age_days(info, item))
            result.files[-1]["device_name"] = str(name) if name else None
            version = info.get("Product Version")
            result.files[-1]["ios_version"] = str(version) if version else None
    except (OSError, PermissionError):
        pass
    return result
