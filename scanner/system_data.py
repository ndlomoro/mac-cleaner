"""System data scanner - finds caches, logs, temp files."""
import fnmatch
import os
from pathlib import Path
from typing import Optional

from utils.helpers import HOME, get_dir_size, file_age_days

# Safe cache directories to scan
# /private/var/folders is deliberately excluded: those top-level dirs are
# live per-user temp roots of running apps, managed by macOS itself. A
# SAFE-badged bulk clean must not offer live per-user temp roots
# (decided 2026-07-18).
CACHE_DIRS = [
    HOME / "Library" / "Caches",
    Path("/tmp"),
    HOME / "tmp",
]

# Dirs cheap enough to walk exhaustively for temp-file patterns.
# Kept as its own name (rather than using CACHE_DIRS directly) because
# tests monkeypatch TEMP_SCAN_DIRS independently of CACHE_DIRS.
TEMP_SCAN_DIRS = list(CACHE_DIRS)

# Safe log directories to scan
LOG_DIRS = [
    HOME / "Library" / "Logs",
    Path("/Library/Logs"),
]

# Temp file patterns
TEMP_PATTERNS = ["*.tmp", "*.temp", "*.log", "*.old", "*.bak", "*.crash", "*.dSYM"]

# Excluded paths that should never be deleted
EXCLUDED = {
    ".DS_Store",
    ".Spotlight-V100",
    ".Trashes",
    ".fseventsd",
    ".DocumentRevisions-V100",
}


class ScanResult:
    """Container for scan results."""
    def __init__(self, category: str, name: str):
        self.category = category
        self.name = name
        self.files: list[dict] = []
        self.total_size = 0
        self.file_count = 0

    def add_file(self, path: str, size: int, age: int):
        self.files.append({
            "path": path,
            "size": size,
            "age_days": age,
        })
        self.total_size += size
        self.file_count += 1

    @property
    def human_size(self) -> str:
        from utils.helpers import format_size
        return format_size(self.total_size)


def scan_caches(min_age_days: int = 7) -> ScanResult:
    """Scan user cache directories for old cache files."""
    result = ScanResult("caches", "User Caches")
    for cache_dir in CACHE_DIRS:
        if not cache_dir.exists():
            continue
        try:
            for item in cache_dir.iterdir():
                if item.name in EXCLUDED:
                    continue
                if item.is_dir():
                    size = get_dir_size(item)
                    age = file_age_days(item)
                    if age >= min_age_days:
                        result.add_file(str(item), size, age)
                elif item.is_file():
                    try:
                        age = file_age_days(item)
                        if age >= min_age_days:
                            result.add_file(
                                str(item), item.stat().st_size, age
                            )
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
    return result


def scan_logs(min_age_days: int = 30) -> ScanResult:
    """Scan log directories for old log files."""
    result = ScanResult("logs", "System & App Logs")
    for log_dir in LOG_DIRS:
        if not log_dir.exists():
            continue
        try:
            for item in log_dir.rglob("*"):
                if not item.is_file():
                    continue
                try:
                    age = file_age_days(item)
                    if age >= min_age_days:
                        result.add_file(
                            str(item), item.stat().st_size, age
                        )
                except (OSError, PermissionError):
                    pass
        except (OSError, PermissionError):
            pass
    return result


def scan_temp_files() -> ScanResult:
    """Scan for temporary files. One walk per cache dir; all patterns matched per file."""
    result = ScanResult("temp", "Temporary Files")
    for cache_dir in TEMP_SCAN_DIRS:
        if not cache_dir.exists():
            continue
        try:
            for item in cache_dir.rglob("*"):
                if not item.is_file():
                    continue
                name = item.name
                if not any(fnmatch.fnmatch(name, pat) for pat in TEMP_PATTERNS):
                    continue
                try:
                    result.add_file(str(item), item.stat().st_size,
                                    file_age_days(item))
                except (OSError, PermissionError):
                    pass
        except (OSError, PermissionError):
            pass
    return result


def scan_downloads() -> ScanResult:
    """Scan Downloads folder. User data: everything is listed; age is a signal only."""
    result = ScanResult("downloads", "Downloads")
    downloads = HOME / "Downloads"
    if not downloads.exists():
        return result
    try:
        for item in downloads.iterdir():
            if item.name in EXCLUDED:
                continue
            try:
                age = file_age_days(item)
                size = get_dir_size(item) if item.is_dir() else item.stat().st_size
                result.add_file(str(item), size, age)
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError):
        pass
    return result


def scan_ios_backups() -> ScanResult:
    """Scan for iOS device backups."""
    result = ScanResult("ios_backups", "iOS Backups")
    backups_dir = HOME / "Library" / "Application Support" / "MobileSync" / "Backup"
    if not backups_dir.exists():
        return result
    try:
        for item in backups_dir.iterdir():
            if item.is_dir():
                size = get_dir_size(item)
                result.add_file(str(item), size, file_age_days(item))
    except (OSError, PermissionError):
        pass
    return result


def scan_all(min_cache_age: int = 7, min_log_age: int = 30) -> list[ScanResult]:
    """Run all Junk scans. Never returns user-data categories (see /CONTEXT.md)."""
    results = [
        scan_caches(min_cache_age),
        scan_logs(min_log_age),
        scan_temp_files(),
    ]
    return [r for r in results if r.file_count > 0]


def scan_space_finder() -> list[ScanResult]:
    """Reclaimable User Data: browse-and-pick only, never bulk-cleaned."""
    results = [scan_downloads(), scan_ios_backups()]
    return [r for r in results if r.file_count > 0]
