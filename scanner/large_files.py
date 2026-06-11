"""Large file finder - discovers space-hogging files."""
from pathlib import Path
from typing import Optional

from utils.helpers import HOME, file_age_days

# Directories to scan for large files
SCAN_DIRS = [
    HOME / "Documents",
    HOME / "Downloads",
    HOME / "Desktop",
    HOME / "Movies",
    HOME / "Music",
    HOME / "Pictures",
    HOME / "Library" / "Application Support",
    HOME / "Library" / "Containers",
]

# File extensions to skip (usually small config/data files)
SKIP_EXTENSIONS = {
    ".plist", ".xml", ".json", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".txt", ".md", ".py", ".js", ".ts", ".jsx",
    ".tsx", ".html", ".css", ".svg", ".ico", ".properties",
}


class LargeFile:
    """Represents a large file found during scan."""
    def __init__(self, path: str, size: int, age_days: int):
        self.path = path
        self.size = size
        self.age_days = age_days

    @property
    def human_size(self) -> str:
        from utils.helpers import format_size
        return format_size(self.size)


def find_large_files(min_size_mb: float = 100,
                     max_results: int = 100) -> list[LargeFile]:
    """Find files larger than min_size_mb across user directories."""
    min_size_bytes = int(min_size_mb * 1024 * 1024)
    results = []

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        try:
            for item in scan_dir.rglob("*"):
                if not item.is_file():
                    continue
                # Skip small file types
                if item.suffix.lower() in SKIP_EXTENSIONS:
                    continue
                try:
                    size = item.stat().st_size
                    if size >= min_size_bytes:
                        results.append(LargeFile(
                            path=str(item),
                            size=size,
                            age_days=file_age_days(item),
                        ))
                except (OSError, PermissionError):
                    pass
        except (OSError, PermissionError):
            pass

    # Sort by size descending
    results.sort(key=lambda x: x.size, reverse=True)
    return results[:max_results]
