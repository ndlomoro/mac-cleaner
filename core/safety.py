"""Protected-path rules. is_protected() is consulted before any deletion."""
from pathlib import Path

HOME = Path.home()

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

    return False, ""
