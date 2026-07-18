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

# Tier 2a: hard-protected user data (children included) - never deletable
HARD_PROTECTED = [
    HOME / "Library" / "Keychains",
    HOME / "Library" / "Mail",
    HOME / "Library" / "Mobile Documents",  # iCloud Drive
    HOME / ".ssh",
    HOME / ".gnupg",
]

# Tier 2b: soft-protected user content - immune to bulk cleaning, but an
# explicitly user-selected pick flow may Trash items here (see CONTEXT.md)
SOFT_PROTECTED = [
    HOME / "Documents",
    HOME / "Desktop",
    HOME / "Pictures",
]


def _match_root(path: Path, roots: list[Path]) -> Path | None:
    for r in roots:
        if path == r or path.is_relative_to(r):
            return r
    return None


def is_protected(path: Path, running: dict[str, str] | None = None,
                 allow_user_content: bool = False) -> tuple[bool, str]:
    """Return (protected, reason). reason is '' when not protected.

    `running` maps bundle-id -> app display name for currently running apps;
    pass {} in tests to disable the live lookup.

    `allow_user_content` lets an explicit, individually-selected pick flow
    Trash items under Soft-Protected roots (~/Documents, ~/Desktop,
    ~/Pictures). It never overrides Hard-Protected locations, system paths,
    Photos libraries, or the Trash itself.
    """
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        return True, "path could not be resolved"

    if resolved in EXACT_PROTECTED:
        return True, f"{resolved} is a top-level system location"

    system_root = _match_root(resolved, SYSTEM_PROTECTED)
    if system_root is not None and _match_root(resolved, SYSTEM_EXEMPT) is None:
        return True, f"macOS system path ({system_root})"

    hard_root = _match_root(resolved, HARD_PROTECTED)
    if hard_root is not None:
        return True, f"personal data ({hard_root})"

    if not allow_user_content:
        soft_root = _match_root(resolved, SOFT_PROTECTED)
        if soft_root is not None:
            return True, f"personal data ({soft_root} - use Space Finder to remove individually)"

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
