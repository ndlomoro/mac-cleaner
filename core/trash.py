"""Trash mechanism. NSFileManager (not send2trash) because it returns the
resulting Trash URL - required for surgical empty (ADR 0001)."""
import shutil
from pathlib import Path


class TrashError(Exception):
    """Trashing failed. Never fall back to permanent delete."""


class NotInTrashError(Exception):
    """Refused to permanently delete a path that is not inside a Trash directory."""


def trash_item(path: Path) -> Path:
    """Move path to the macOS Trash. Returns its actual location inside the Trash."""
    from Foundation import NSURL, NSFileManager  # lazy: macOS only

    fm = NSFileManager.defaultManager()
    url = NSURL.fileURLWithPath_(str(path))
    ok, result_url, error = fm.trashItemAtURL_resultingItemURL_error_(url, None, None)
    if not ok:
        detail = str(error.localizedDescription()) if error else "unknown error"
        raise TrashError(f"could not move {path} to Trash: {detail}")
    return Path(str(result_url.path()))


def delete_from_trash(trash_path: Path) -> None:
    """Permanently delete an item we previously trashed. Guarded: the path must
    live inside a .Trash/.Trashes directory - this function must never be able
    to touch anything else.

    The parent chain is resolved (collapsing `..` segments and following any
    symlinked ancestor directories) before the Trash-membership check, so
    escapes via `..` or a symlinked ancestor are rejected. The final component
    itself is deliberately NOT resolved: a legitimately-trashed item may be a
    symlink, and resolving it would follow the link outside the Trash and
    wrongly reject a valid delete."""
    normalized = trash_path.parent.resolve() / trash_path.name
    if not any(part in (".Trash", ".Trashes") for part in normalized.parts):
        raise NotInTrashError(f"{trash_path} is not inside a Trash directory")
    if normalized.is_dir() and not normalized.is_symlink():
        shutil.rmtree(normalized, ignore_errors=False)
    elif normalized.exists() or normalized.is_symlink():
        normalized.unlink()
