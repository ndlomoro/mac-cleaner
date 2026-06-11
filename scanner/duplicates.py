"""Duplicate file finder - detects duplicate files by content hash."""
import hashlib
from pathlib import Path
from collections import defaultdict

from utils.helpers import HOME

# Directories to scan for duplicates
SCAN_DIRS = [
    HOME / "Documents",
    HOME / "Downloads",
    HOME / "Desktop",
    HOME / "Pictures",
    HOME / "Movies",
    HOME / "Music",
]

# Skip these extensions (text/config files rarely worth deduplicating)
SKIP_EXTENSIONS = {
    ".plist", ".xml", ".json", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".txt", ".md", ".py", ".js", ".ts", ".jsx",
    ".tsx", ".html", ".css", ".svg", ".ico", ".log",
}


def _file_hash(filepath: Path, chunk_size: int = 65536) -> str:
    """Compute MD5 hash of a file."""
    hasher = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, PermissionError):
        return ""


def find_duplicates(min_size_bytes: int = 10240) -> list[dict]:
    """
    Find duplicate files by size first, then by content hash.
    Returns list of groups, each group is a dict with:
      - hash: the MD5 hash
      - size: file size in bytes
      - files: list of file paths
      - wasted: size * (count - 1)
    """
    # Phase 1: Group files by size
    size_groups = defaultdict(list)
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        try:
            for item in scan_dir.rglob("*"):
                if not item.is_file():
                    continue
                if item.suffix.lower() in SKIP_EXTENSIONS:
                    continue
                try:
                    size = item.stat().st_size
                    if size >= min_size_bytes:
                        size_groups[size].append(item)
                except (OSError, PermissionError):
                    pass
        except (OSError, PermissionError):
            pass

    # Phase 2: For size groups with multiple files, check content hash
    duplicates = []
    for size, files in size_groups.items():
        if len(files) < 2:
            continue
        hash_groups = defaultdict(list)
        for f in files:
            h = _file_hash(f)
            if h:
                hash_groups[h].append(str(f))
        for h, paths in hash_groups.items():
            if len(paths) >= 2:
                duplicates.append({
                    "hash": h,
                    "size": size,
                    "files": paths,
                    "wasted": size * (len(paths) - 1),
                })

    # Sort by wasted space descending
    duplicates.sort(key=lambda x: x["wasted"], reverse=True)
    return duplicates
