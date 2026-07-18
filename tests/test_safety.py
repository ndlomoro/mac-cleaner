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


@pytest.mark.parametrize("path", [
    HOME / "Documents" / "big-video.mov",
    HOME / "Desktop" / "old-export.zip",
    HOME / "Pictures" / "dupes" / "IMG_0001 copy.jpg",
])
def test_soft_protected_yields_to_user_selection(path):
    protected, _ = is_protected(path, running={})
    assert protected  # default: still protected
    protected, _ = is_protected(path, running={}, allow_user_content=True)
    assert not protected  # explicit user selection may delete Soft-Protected content


@pytest.mark.parametrize("path", [
    HOME / "Library" / "Keychains" / "login.keychain-db",
    HOME / "Library" / "Mail" / "V10",
    HOME / ".ssh" / "id_ed25519",
    HOME / ".gnupg" / "private-keys-v1.d",
    HOME / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "f",
    Path("/System/Library/CoreServices"),
])
def test_hard_protected_never_yields(path):
    protected, _ = is_protected(path, running={}, allow_user_content=True)
    assert protected


def test_photoslibrary_and_trash_never_yield(tmp_path):
    lib = tmp_path / "P.photoslibrary" / "db"
    lib.mkdir(parents=True)
    assert is_protected(lib, running={}, allow_user_content=True)[0]
    assert is_protected(HOME / ".Trash" / "x", running={}, allow_user_content=True)[0]


def test_symlink_escape_caught(tmp_path):
    # a symlink inside a "cache" dir pointing into ~/Documents must be protected
    target = HOME / "Documents"
    link = tmp_path / "sneaky-cache-entry"
    link.symlink_to(target)
    protected, _ = is_protected(link, running={})
    assert protected


from core.safety import Owner, owning_app


def test_owning_app_bundle_id_cache_dir():
    p = HOME / "Library" / "Caches" / "com.tinyspeck.slackmacgap" / "Cache" / "f_0001"
    owner = owning_app(p)
    assert owner is not None
    assert owner.bundle_id == "com.tinyspeck.slackmacgap"


def test_owning_app_browser_profile_map():
    p = HOME / "Library" / "Application Support" / "Google" / "Chrome" / "Default" / "History"
    owner = owning_app(p)
    assert owner == Owner("com.google.Chrome", "Chrome")


def test_owning_app_none_for_ownerless_junk():
    assert owning_app(Path("/tmp/foo.tmp")) is None
    assert owning_app(Path("/private/var/folders/ab/xyz")) is None
    # non-bundle-id cache folder name (no dot)
    assert owning_app(HOME / "Library" / "Caches" / "SomeToolCache") is None


def test_in_use_protected_when_owner_running():
    p = HOME / "Library" / "Caches" / "com.tinyspeck.slackmacgap" / "Cache"
    protected, reason = is_protected(
        p, running={"com.tinyspeck.slackmacgap": "Slack"}
    )
    assert protected
    assert reason == "Slack is running"


def test_not_protected_when_owner_quit():
    p = HOME / "Library" / "Caches" / "com.tinyspeck.slackmacgap" / "Cache"
    protected, _ = is_protected(p, running={"com.apple.finder": "Finder"})
    assert not protected
