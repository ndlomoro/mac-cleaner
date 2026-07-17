from pathlib import Path

import pytest

from core.safety import is_protected

HOME = Path.home()


@pytest.mark.parametrize("path", [
    Path("/System/Library/CoreServices"),
    Path("/bin/ls"),
    Path("/sbin/mount"),
    Path("/usr/lib/dyld"),
    Path("/private/var/db/dslocal"),
    Path("/Library/Apple/System"),
])
def test_system_paths_protected(path):
    protected, reason = is_protected(path, running={})
    assert protected
    assert reason


@pytest.mark.parametrize("path", [
    HOME / "Documents" / "taxes.pdf",
    HOME / "Desktop" / "notes.txt",
    HOME / "Pictures" / "wedding",
    HOME / "Library" / "Keychains" / "login.keychain-db",
    HOME / "Library" / "Mail" / "V10",
    HOME / ".ssh" / "id_ed25519",
    HOME / ".gnupg" / "private-keys-v1.d",
    HOME / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "file",
])
def test_user_data_protected(path):
    protected, reason = is_protected(path, running={})
    assert protected
    assert reason


@pytest.mark.parametrize("path", [
    Path("/"),
    Path("/Applications"),
    Path("/Users"),
    Path("/Library"),
    HOME,
])
def test_top_level_roots_protected(path):
    protected, _ = is_protected(path, running={})
    assert protected


def test_photoslibrary_protected_anywhere(tmp_path):
    lib = tmp_path / "My Photos.photoslibrary" / "database"
    lib.mkdir(parents=True)
    protected, reason = is_protected(lib, running={})
    assert protected
    assert "Photos" in reason


def test_trash_itself_protected():
    protected, reason = is_protected(HOME / ".Trash" / "old.txt", running={})
    assert protected


def test_component_boundary_not_prefix(tmp_path):
    # /Systemwide is NOT /System; a dir merely *named* Documents outside HOME is fine
    d = tmp_path / "Systemwide"
    d.mkdir()
    protected, _ = is_protected(d, running={})
    assert not protected


@pytest.mark.parametrize("path", [
    Path("/usr/local/lib/something"),   # /usr/local is exempt
    Path("/tmp/scratch.tmp"),
    HOME / "Library" / "Caches" / "some.app.cache",
])
def test_junk_locations_not_protected(path):
    protected, _ = is_protected(path, running={})
    assert not protected


def test_symlink_escape_caught(tmp_path):
    # a symlink inside a "cache" dir pointing into ~/Documents must be protected
    target = HOME / "Documents"
    link = tmp_path / "sneaky-cache-entry"
    link.symlink_to(target)
    protected, _ = is_protected(link, running={})
    assert protected
