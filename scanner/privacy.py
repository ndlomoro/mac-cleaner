"""Privacy cleaner - finds and removes browser history, tracking data, and private files."""
from pathlib import Path

from utils.helpers import HOME, get_dir_size

# Browser cache and history locations
BROWSER_PATHS = {
    "Safari": {
        "caches": HOME / "Library" / "Caches" / "com.apple.Safari",
        "history": HOME / "Library" / "Safari" / "History.db",
        "downloads": HOME / "Library" / "Safari" / "Downloads.plist",
    },
    "Chrome": {
        "caches": HOME / "Library" / "Caches" / "Google" / "Chrome",
        "history": HOME / "Library" / "Application Support" / "Google" / "Chrome" / "Default" / "History",
    },
    "Firefox": {
        "caches": HOME / "Library" / "Caches" / "Mozilla" / "Firefox" / "Profiles",
    },
}

# Tracking and privacy-related paths
TRACKING_PATHS = [
    HOME / "Library" / "DiagnosticReports",
    HOME / "Library" / "Internet Plug-Ins" / "Cache",
    HOME / "Library" / "Preferences" / "ByHost",
]


def scan_browser_data() -> list[dict]:
    """Scan browser cache and history files."""
    results = []
    for browser, paths in BROWSER_PATHS.items():
        for key, path in paths.items():
            if path.exists():
                try:
                    if path.is_dir():
                        size = get_dir_size(path)
                    else:
                        size = path.stat().st_size
                    results.append({
                        "browser": browser,
                        "type": key,
                        "path": str(path),
                        "size": size,
                    })
                except (OSError, PermissionError):
                    pass
    return results


def scan_tracking_data() -> list[dict]:
    """Scan tracking and diagnostic data."""
    results = []
    for path in TRACKING_PATHS:
        if path.exists():
            try:
                if path.is_dir():
                    size = get_dir_size(path)
                    results.append({
                        "type": "tracking_dir",
                        "path": str(path),
                        "size": size,
                    })
                else:
                    results.append({
                        "type": "tracking_file",
                        "path": str(path),
                        "size": path.stat().st_size,
                    })
            except (OSError, PermissionError):
                pass
    return results


def scan_recently_used() -> list[dict]:
    """Scan recently used items (Recents, dock items)."""
    results = []
    recents = HOME / "Library" / "Preferences" / "com.apple.recentitems"
    if recents.exists():
        try:
            results.append({
                "type": "recent_items",
                "path": str(recents),
                "size": recents.stat().st_size,
            })
        except (OSError, PermissionError):
            pass
    return results
