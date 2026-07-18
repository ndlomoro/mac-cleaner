"""Mail junk scanner - attachment copies and caches ONLY.

~/Library/Mail (mailbox content) is Hard-Protected and this module is
structurally unable to emit paths under it (see _outside_mail_store).
"""
from pathlib import Path

from scanner.system_data import ScanResult
from utils.helpers import HOME, file_age_days, get_dir_size

_CONTAINER = HOME / "Library" / "Containers" / "com.apple.mail" / "Data" / "Library"

MAIL_DOWNLOAD_DIRS = [
    _CONTAINER / "Mail Downloads",
    HOME / "Library" / "Mail Downloads",  # legacy location - sibling of Mail, not child
]
MAIL_CACHE_DIRS = [
    HOME / "Library" / "Caches" / "com.apple.mail",
    _CONTAINER / "Caches",
]


def _outside_mail_store(path: Path) -> bool:
    return not path.resolve().is_relative_to((HOME / "Library" / "Mail").resolve())


def _scan_dirs(dirs: list[Path], category: str, name: str) -> ScanResult:
    result = ScanResult(category, name)
    for root in dirs:
        if not root.exists() or not _outside_mail_store(root):
            continue
        try:
            for item in root.iterdir():
                if not _outside_mail_store(item):
                    continue
                try:
                    size = get_dir_size(item) if item.is_dir() else item.stat().st_size
                    result.add_file(str(item), size, int(file_age_days(item)))
                except (OSError, PermissionError):
                    pass
        except (OSError, PermissionError):
            pass
    return result


def scan_mail_downloads() -> ScanResult:
    return _scan_dirs(MAIL_DOWNLOAD_DIRS, "mail_downloads", "Mail Attachment Copies")


def scan_mail_cache() -> ScanResult:
    return _scan_dirs(MAIL_CACHE_DIRS, "mail_cache", "Mail Caches")


def scan_mail_junk() -> list[ScanResult]:
    return [r for r in (scan_mail_downloads(), scan_mail_cache()) if r.file_count > 0]
