"""App uninstaller with leftover detection."""
from pathlib import Path

from utils.helpers import HOME, LIBRARY, get_dir_size

# Common locations for app leftover files
LEFTOVER_PATHS = [
    # Library directories
    (LIBRARY / "Application Support", "{app}*", "{app}"),
    (LIBRARY / "Preferences", "com.*{app}*", "*{app}*"),
    (LIBRARY / "Caches", "com.*{app}*", "*{app}*"),
    (LIBRARY / "Containers", "com.*{app}*"),
    (LIBRARY / "Saved Application State", "com.*{app}*.savedState"),
    (LIBRARY / "HTTPStorages", "com.*{app}*"),
    (LIBRARY / "IdentityServices", "com.*{app}*"),
    (LIBRARY / "WebKit", "*{app}*"),
    (LIBRARY / "Group Containers", "*{app}*"),
    # System library
    (Path("/Library/Caches"), "com.*{app}*"),
    (Path("/Library/Preferences"), "com.*{app}*"),
]


def find_leftovers(app_name: str) -> list[dict]:
    """Find leftover files for an uninstalled app."""
    leftovers = []
    name_lower = app_name.lower()

    for base_dir, *patterns in LEFTOVER_PATHS:
        if not base_dir.exists():
            continue
        for pattern in patterns:
            search = pattern.replace("{app}", app_name)
            try:
                for item in base_dir.rglob(search):
                    if item.is_file() or item.is_dir():
                        try:
                            size = get_dir_size(item) if item.is_dir() else item.stat().st_size
                            leftovers.append({
                                "path": str(item),
                                "size": size,
                                "type": "dir" if item.is_dir() else "file",
                            })
                        except (OSError, PermissionError):
                            pass
            except (OSError, PermissionError):
                pass

    # Also check by lowercase name match
    for base_dir, *patterns in LEFTOVER_PATHS:
        if not base_dir.exists():
            continue
        try:
            for item in base_dir.iterdir():
                if name_lower in item.name.lower() and item.name.lower() != name_lower:
                    already = any(str(item) in [l["path"] for l in leftovers])
                    if not already:
                        try:
                            size = get_dir_size(item) if item.is_dir() else item.stat().st_size
                            leftovers.append({
                                "path": str(item),
                                "size": size,
                                "type": "dir" if item.is_dir() else "file",
                            })
                        except (OSError, PermissionError):
                            pass
        except (OSError, PermissionError):
            pass

    return leftovers


def get_installed_apps() -> list[dict]:
    """Get list of installed .app bundles."""
    apps = []
    apps_dir = Path("/Applications")
    if not apps_dir.exists():
        return apps
    for app in apps_dir.glob("*.app"):
        try:
            size = get_dir_size(app)
            apps.append({
                "name": app.name.replace(".app", ""),
                "path": str(app),
                "size": size,
            })
        except (OSError, PermissionError):
            pass
    apps.sort(key=lambda x: x["size"], reverse=True)
    return apps
