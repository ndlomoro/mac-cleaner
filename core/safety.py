"""Protected-path rules. is_protected() is consulted before any deletion."""
from dataclasses import dataclass
from pathlib import Path

HOME = Path.home()


@dataclass(frozen=True)
class Owner:
    bundle_id: str
    app_name: str


# Paths that don't self-identify their owner (browser profiles etc.)
KNOWN_OWNERS = {
    HOME / "Library" / "Safari": Owner("com.apple.Safari", "Safari"),
    HOME / "Library" / "Caches" / "com.apple.Safari": Owner("com.apple.Safari", "Safari"),
    HOME / "Library" / "Caches" / "Google" / "Chrome": Owner("com.google.Chrome", "Chrome"),
    HOME / "Library" / "Application Support" / "Google" / "Chrome": Owner("com.google.Chrome", "Chrome"),
    HOME / "Library" / "Caches" / "Mozilla" / "Firefox": Owner("org.mozilla.firefox", "Firefox"),
    HOME / "Library" / "Application Support" / "Firefox": Owner("org.mozilla.firefox", "Firefox"),
}

_CACHES_ROOT = HOME / "Library" / "Caches"


def owning_app(resolved: Path) -> Owner | None:
    """Best-effort owner of a junk path. None = ownerless (always deletable)."""
    for prefix, owner in KNOWN_OWNERS.items():
        if resolved == prefix or resolved.is_relative_to(prefix):
            return owner
    if resolved != _CACHES_ROOT and resolved.is_relative_to(_CACHES_ROOT):
        first = resolved.relative_to(_CACHES_ROOT).parts[0]
        if "." in first:  # looks like a reverse-DNS bundle id
            return Owner(first, first)
    return None


def running_apps() -> dict[str, str]:
    """bundle-id -> localized name for currently running apps (one snapshot per clean run)."""
    from AppKit import NSWorkspace  # imported lazily: not available under CI/Linux

    apps: dict[str, str] = {}
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        bid = app.bundleIdentifier()
        if bid:
            apps[str(bid)] = str(app.localizedName() or bid)
    return apps

# Tier 0: exact top-level roots that must never be deleted themselves
EXACT_PROTECTED = {
    Path("/"),
    Path("/Applications"),
    Path("/Users"),
    Path("/Library"),
    Path("/System"),
    Path("/private"),
    HOME,
}

# Tier 1: system-critical trees (children included)
SYSTEM_PROTECTED = [
    Path("/System"),
    Path("/bin"),
    Path("/sbin"),
    Path("/usr"),
    Path("/private/var/db"),
    Path("/Library/Apple"),
]
SYSTEM_EXEMPT = [
    Path("/usr/local"),
]

# Tier 2: user-data trees (children included)
USER_PROTECTED = [
    HOME / "Documents",
    HOME / "Desktop",
    HOME / "Pictures",
    HOME / "Library" / "Keychains",
    HOME / "Library" / "Mail",
    HOME / "Mobile Documents",            # just in case
    HOME / "Library" / "Mobile Documents",  # iCloud Drive
    HOME / ".ssh",
    HOME / ".gnupg",
]


def _under_any(path: Path, roots: list[Path]) -> bool:
    return any(path == r or path.is_relative_to(r) for r in roots)


def is_protected(path: Path, running: dict[str, str] | None = None) -> tuple[bool, str]:
    """Return (protected, reason). reason is '' when not protected.

    `running` maps bundle-id -> app display name for currently running apps;
    pass {} in tests to disable the live lookup.
    """
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return True, "path could not be resolved"

    if resolved in EXACT_PROTECTED:
        return True, f"{resolved} is a top-level system location"

    if _under_any(resolved, SYSTEM_PROTECTED) and not _under_any(resolved, SYSTEM_EXEMPT):
        return True, "macOS system path"

    if _under_any(resolved, USER_PROTECTED):
        return True, "personal data (protected location)"

    for part in resolved.parts:
        if part.endswith(".photoslibrary"):
            return True, "Photos library"
        if part in (".Trash", ".Trashes"):
            return True, "already in the Trash"

    owner = owning_app(resolved)
    if owner is not None:
        active = running if running is not None else running_apps()
        if owner.bundle_id in active:
            return True, f"{active[owner.bundle_id]} is running"

    return False, ""
