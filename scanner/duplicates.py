"""Duplicate file finder - detects duplicate files by content hash."""
import hashlib
from pathlib import Path
from collections import defaultdict

from utils.helpers import HOME, file_age_days

# Directories to scan for duplicates
SCAN_DIRS = [
    HOME / "Documents",
    HOME / "Downloads",
    HOME / "Desktop",
    HOME / "Pictures",
    HOME / "Movies",
    HOME / "Music",
]

# Directories whose contents are preferred as the "keeper" copy of a
# duplicate group - user-curated locations rather than scratch space like
# Downloads or Desktop.
CANONICAL_DIRS = [
    HOME / "Pictures",
    HOME / "Documents",
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


def _partial_hash(filepath: Path, length: int = 65536) -> str:
    """Compute MD5 hash of exactly the first `length` bytes of a file.

    Used as a cheap pre-filter before the full-file hash: files whose
    size matches but whose first 64KB differ can't be duplicates, so
    they never pay for a full read.
    """
    hasher = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(length)
        hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, PermissionError):
        return ""


def find_duplicates(min_size_bytes: int = 1_000_000) -> list[dict]:
    """
    Find duplicate files via three stages: size, then partial (first-64KB)
    hash, then full-content hash - so full hashing only ever runs on files
    that already agree on size and on their first 64KB.
    Returns list of groups, each group is a dict with:
      - hash: the full MD5 hash
      - size: file size in bytes
      - files: list of file paths
      - wasted: size * (count - 1)
    """
    # Stage 1: Group files by size
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
                if any(part.lower().endswith(".photoslibrary")
                       for part in item.parts):
                    # Hard-protected bundle contents can never be deleted -
                    # hashing them wastes hours and yields dead rows.
                    continue
                try:
                    size = item.stat().st_size
                    if size >= min_size_bytes:
                        size_groups[size].append(item)
                except (OSError, PermissionError):
                    pass
        except (OSError, PermissionError):
            pass

    duplicates = []
    for size, files in size_groups.items():
        if len(files) < 2:
            continue

        # Stage 2: within a size group, pre-filter by first-64KB hash
        partial_groups = defaultdict(list)
        for f in files:
            ph = _partial_hash(f)
            if ph:
                partial_groups[ph].append(f)

        # Stage 3: only multi-member (size, partial) groups pay for a
        # full-content hash
        for partial_files in partial_groups.values():
            if len(partial_files) < 2:
                continue
            hash_groups = defaultdict(list)
            for f in partial_files:
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


def _is_canonical(path: Path) -> bool:
    """True if `path` sits under any CANONICAL_DIRS entry (no filesystem access)."""
    return any(path.is_relative_to(d) for d in CANONICAL_DIRS)


def pick_keeper(paths: list[str]) -> str:
    """Pick which copy of a duplicate group to KEEP.

    Preference order (most-preferred first):
      1. Path is under a CANONICAL_DIRS location.
      2. Fewer path components (shallower).
      3. Older mtime (larger file_age_days wins) - missing files count as
         age 0 and never raise.
      4. Lexicographic order, as a final total order.
    """
    if not paths:
        raise ValueError("pick_keeper requires at least one path")

    def sort_key(p: str) -> tuple:
        path = Path(p)
        canonical = 0 if _is_canonical(path) else 1
        depth = len(path.parts)
        age = file_age_days(path)
        return (canonical, depth, -age, p)

    return min(paths, key=sort_key)
