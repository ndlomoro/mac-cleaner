# Safety Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One engine (`core/`) owns every destructive action: Trash-only deletion via NSFileManager, hardened protected paths with explainable skips, a category safety registry, honest Trashed/Reclaimed reporting, and gated Irreversible Actions.

**Architecture:** New `core/` package (`registry.py`, `safety.py`, `trash.py`, `deleter.py`). The four existing cleaners become thin orchestration over `core.deleter.safe_delete()`. `scan_all()` shrinks to Junk-only; downloads/iOS backups move to a Space Finder pick-list. `main.py` gets minimal truthful wiring (wording, gates, skip reasons) — no visual polish.

**Tech Stack:** Python 3.11, Rich (existing UI), PyObjC (`pyobjc-framework-Cocoa`) for `NSFileManager.trashItemAtURL` and `NSWorkspace.runningApplications`, pytest.

**Spec:** `docs/superpowers/specs/2026-07-16-safety-core-design.md`. **Vocabulary:** `/CONTEXT.md` — use "Trashed"/"moved to Trash" (never "freed") for trash moves; "Reclaimed" only for actual disk-space return.

## Global Constraints

- macOS-only; Python ≥ 3.11.
- `safe_delete` is the only function allowed to destroy file data. Irreversible Actions (snapshots, recents) keep their mechanisms but consult the registry.
- Never fall back from Trash failure to permanent delete.
- `user_data` categories require `user_selected=True` (tripwire) — and the UI must only pass individually selected items.
- All new code TDD: failing test → minimal implementation → pass → commit.
- Run tests from repo root: `python3 -m pytest tests/ -v`.
- New dependency: `pyobjc-framework-Cocoa>=10.0`. Removed at the end: `send2trash`.

---

### Task 0: Baseline commit

The working tree has uncommitted WIP (`main.py`, `scanner/app_remnants.py`, `tests/test_large_files.py`) and 7 untracked test files. Commit them as the baseline so every later commit is reviewable.

**Files:**
- Modify: `.gitignore` (add `.DS_Store`)
- Commit: all modified + untracked test files

- [ ] **Step 1: Ignore .DS_Store**

Append to `.gitignore`:

```
.DS_Store
```

- [ ] **Step 2: Verify the existing suite passes**

Run: `python3 -m pytest tests/ -v`
Expected: all tests pass (if any fail, STOP and report — do not fix unrelated failures silently).

- [ ] **Step 3: Commit baseline**

```bash
git add .gitignore main.py scanner/app_remnants.py tests/
git commit -m "chore: commit WIP baseline (tests + UI tweaks) before safety core"
```

---

### Task 1: Category registry (`core/registry.py`)

**Files:**
- Create: `core/__init__.py` (empty)
- Create: `core/registry.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Produces: `Level` (str-Enum: SAFE/CAUTION/RISKY), `Category` dataclass (`key, level, explanation, user_data, via_trash`, property `irreversible`), `get(key) -> Category` raising `UnknownCategoryError`, `REGISTRY: dict[str, Category]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_registry.py`:

```python
import pytest
from core.registry import REGISTRY, Category, Level, UnknownCategoryError, get


def test_get_known_category():
    cat = get("caches")
    assert cat.key == "caches"
    assert cat.level is Level.SAFE
    assert cat.via_trash is True
    assert cat.user_data is False


def test_get_unknown_category_raises():
    with pytest.raises(UnknownCategoryError):
        get("nonexistent_category")


def test_every_entry_has_explanation():
    for cat in REGISTRY.values():
        assert cat.explanation.strip(), f"{cat.key} has no explanation"


def test_irreversible_is_exactly_risky_non_trash():
    irreversible = {k for k, c in REGISTRY.items() if c.irreversible}
    assert irreversible == {"recents", "snapshots"}


def test_user_data_categories():
    user_data = {k for k, c in REGISTRY.items() if c.user_data}
    assert user_data == {"downloads", "ios_backups"}


def test_non_trash_junk_is_not_irreversible():
    # brew/npm bypass Trash but are SAFE -> labeled, never gated
    assert REGISTRY["brew_cleanup"].via_trash is False
    assert REGISTRY["brew_cleanup"].irreversible is False
    assert REGISTRY["npm_cache"].irreversible is False


def test_all_cleaner_categories_registered():
    # every category any cleaner passes to safe_delete
    for key in [
        "caches", "logs", "temp", "downloads", "ios_backups",
        "browser_cache", "browser_history", "tracking_data", "recents",
        "app_bundle", "app_leftovers", "launch_agents",
        "xcode_derived_data", "cocoapods_cache", "pip_cache",
        "brew_cleanup", "npm_cache", "snapshots",
    ]:
        assert key in REGISTRY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core'`

- [ ] **Step 3: Implement the registry**

Create empty `core/__init__.py`, then `core/registry.py`:

```python
"""Category safety registry - every cleanable category must be declared here."""
from dataclasses import dataclass
from enum import Enum


class Level(str, Enum):
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    RISKY = "RISKY"


class UnknownCategoryError(KeyError):
    """Raised when a category is not declared in the registry."""


@dataclass(frozen=True)
class Category:
    key: str
    level: Level
    explanation: str
    user_data: bool = False   # True -> individual explicit selection required
    via_trash: bool = True    # False -> external tool / in-place mechanism

    @property
    def irreversible(self) -> bool:
        """Irreversible Action: RISKY and cannot go through the Trash. Gets the typed gate."""
        return not self.via_trash and self.level is Level.RISKY


_CATEGORIES = [
    Category("caches", Level.SAFE,
             "Temporary files apps rebuild automatically; first launches may be slower afterwards."),
    Category("logs", Level.SAFE,
             "Diagnostic text files apps write for troubleshooting; nothing reads them back."),
    Category("temp", Level.SAFE,
             "Leftover working files (*.tmp, *.bak, crash reports) no app will miss."),
    Category("browser_cache", Level.SAFE,
             "Saved copies of web pages; browsers re-download them, so pages load slower once."),
    Category("xcode_derived_data", Level.SAFE,
             "Xcode build products; the next build regenerates them from source."),
    Category("cocoapods_cache", Level.SAFE,
             "Downloaded CocoaPods packages; 'pod install' re-fetches what projects need."),
    Category("pip_cache", Level.SAFE,
             "Downloaded Python packages; pip re-fetches them on the next install."),
    Category("brew_cleanup", Level.SAFE,
             "Old Homebrew downloads and outdated versions; brew re-downloads on demand.",
             via_trash=False),
    Category("npm_cache", Level.SAFE,
             "Downloaded npm packages; npm re-fetches them on the next install.",
             via_trash=False),
    Category("app_bundle", Level.CAUTION,
             "The application itself; uninstalling removes it from /Applications."),
    Category("app_leftovers", Level.CAUTION,
             "Settings and support files left behind by an app; removing them resets the app."),
    Category("launch_agents", Level.CAUTION,
             "Programs set to run automatically at login; removing one stops that behavior."),
    Category("tracking_data", Level.RISKY,
             "Diagnostic reports and per-host preferences; may include data you'd rather keep private."),
    Category("browser_history", Level.RISKY,
             "Your browsing history; once cleared, it cannot be recovered from the browser."),
    Category("downloads", Level.RISKY,
             "Files you downloaded - real documents, not junk. Review each one before removing.",
             user_data=True),
    Category("ios_backups", Level.RISKY,
             "Device backups - possibly the only copy of a phone's data. Review each one.",
             user_data=True),
    Category("recents", Level.RISKY,
             "The list of recently opened files; clearing rewrites it in place and cannot be undone.",
             via_trash=False),
    Category("snapshots", Level.RISKY,
             "Time Machine restore points; deleting one permanently removes that restore point.",
             via_trash=False),
]

REGISTRY: dict[str, Category] = {c.key: c for c in _CATEGORIES}


def get(key: str) -> Category:
    try:
        return REGISTRY[key]
    except KeyError:
        raise UnknownCategoryError(
            f"Category '{key}' is not registered. Every cleanable category must be "
            f"declared in core/registry.py with a level and explanation."
        ) from None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_registry.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add core/ tests/test_registry.py
git commit -m "feat: add category safety registry (level, user_data, via_trash)"
```

---

### Task 2: Protected paths (`core/safety.py`, tiers 1-2)

**Files:**
- Create: `core/safety.py`
- Test: `tests/test_safety.py`

**Interfaces:**
- Produces: `is_protected(path: Path, running: dict[str, str] | None = None) -> tuple[bool, str]`. Empty reason string when not protected. (`running` is used in Task 3; this task implements static tiers only and accepts the parameter.)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_safety.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_safety.py -v`
Expected: FAIL with `ImportError` (core.safety does not exist)

- [ ] **Step 3: Implement static protection tiers**

Create `core/safety.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_safety.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add core/safety.py tests/test_safety.py
git commit -m "feat: protected-path rules (system, user-data, exact roots, symlink-safe)"
```

---

### Task 3: In-Use protection (`core/safety.py`, tier 3)

**Files:**
- Modify: `core/safety.py` (append)
- Test: `tests/test_safety.py` (append)

**Interfaces:**
- Produces: `running_apps() -> dict[str, str]` (bundle-id → localized name, live via NSWorkspace), `owning_app(resolved: Path) -> Owner | None` where `Owner(bundle_id: str, app_name: str)`. `is_protected` gains the tier-3 check: owner running → `(True, "<App> is running")`.
- Consumes: PyObjC AppKit (installed in Task 4's requirements step — for THIS task, install it first: `pip3 install "pyobjc-framework-Cocoa>=10.0"`).

- [ ] **Step 1: Install PyObjC now (needed by the import)**

Run: `pip3 install "pyobjc-framework-Cocoa>=10.0"`
Expected: installs successfully (macOS only).

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_safety.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_safety.py -v -k "owning or in_use or owner_quit"`
Expected: FAIL with `ImportError: cannot import name 'Owner'`

- [ ] **Step 4: Implement in-use protection**

In `core/safety.py`, add after the imports:

```python
from dataclasses import dataclass


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
```

Then, in `is_protected`, replace the final `return False, ""` with:

```python
    owner = owning_app(resolved)
    if owner is not None:
        active = running if running is not None else running_apps()
        if owner.bundle_id in active:
            return True, f"{active[owner.bundle_id]} is running"

    return False, ""
```

- [ ] **Step 5: Run the whole safety suite**

Run: `python3 -m pytest tests/test_safety.py -v`
Expected: all pass (earlier tests pass `running={}` so no live lookup happens)

- [ ] **Step 6: Commit**

```bash
git add core/safety.py tests/test_safety.py
git commit -m "feat: In Use protection - junk owned by a running app is skipped by name"
```

---

### Task 4: Trash mechanism (`core/trash.py`)

**Files:**
- Create: `core/trash.py`
- Modify: `requirements.txt`
- Test: `tests/test_trash.py`

**Interfaces:**
- Produces: `trash_item(path: Path) -> Path` (returns the item's actual location inside the Trash; raises `TrashError` on failure), `delete_from_trash(trash_path: Path) -> None` (permanent delete; raises `NotInTrashError` unless the path is inside a `.Trash`/`.Trashes` directory).

- [ ] **Step 1: Update requirements.txt**

Replace the full contents of `requirements.txt` with:

```
rich>=13.7.0
send2trash>=1.8.3
pyobjc-framework-Cocoa>=10.0
pytest>=8.0.0
```

(send2trash is removed later, in Task 13, once no module imports it.)

- [ ] **Step 2: Write the failing tests**

Create `tests/test_trash.py`:

```python
from pathlib import Path

import pytest

from core.trash import NotInTrashError, TrashError, delete_from_trash, trash_item


def test_trash_roundtrip_and_surgical_delete(tmp_path):
    """Integration: really trash a file, get its Trash location, permanently delete it."""
    victim = tmp_path / "mac-cleaner-test-victim.txt"
    victim.write_text("delete me")

    trash_path = trash_item(victim)

    assert not victim.exists()
    assert trash_path.exists()
    assert any(part in (".Trash", ".Trashes") for part in trash_path.parts)

    delete_from_trash(trash_path)
    assert not trash_path.exists()


def test_trash_missing_file_raises(tmp_path):
    with pytest.raises(TrashError):
        trash_item(tmp_path / "never-existed.txt")


def test_delete_from_trash_refuses_paths_outside_trash(tmp_path):
    innocent = tmp_path / "innocent.txt"
    innocent.write_text("keep me")
    with pytest.raises(NotInTrashError):
        delete_from_trash(innocent)
    assert innocent.exists()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_trash.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.trash'`

- [ ] **Step 4: Implement the trash wrapper**

Create `core/trash.py`:

```python
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
    to touch anything else."""
    if not any(part in (".Trash", ".Trashes") for part in trash_path.parts):
        raise NotInTrashError(f"{trash_path} is not inside a Trash directory")
    if trash_path.is_dir() and not trash_path.is_symlink():
        shutil.rmtree(trash_path, ignore_errors=False)
    elif trash_path.exists() or trash_path.is_symlink():
        trash_path.unlink()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_trash.py -v`
Expected: 3 passed (the roundtrip test really uses your Trash, then cleans up after itself)

- [ ] **Step 6: Commit**

```bash
git add core/trash.py tests/test_trash.py requirements.txt
git commit -m "feat: NSFileManager trash wrapper returning Trash locations (ADR 0001)"
```

---

### Task 5: The deletion engine (`core/deleter.py`)

**Files:**
- Create: `core/deleter.py`
- Test: `tests/test_deleter.py`

**Interfaces:**
- Consumes: `core.registry.get`, `core.safety.is_protected`, `core.safety.running_apps`, `core.trash.trash_item`.
- Produces:
  - `Outcome` (str-Enum: TRASHED/SKIPPED/FAILED), `PathResult(path, outcome, size, reason, trash_path)`.
  - `DeleteReport(category, dry_run, results)` with properties `trashed: list[PathResult]`, `skipped: list[PathResult]`, `failed: list[PathResult]`, `trashed_bytes: int`.
  - `safe_delete(items: list[dict], category: str, dry_run: bool = False, user_selected: bool = False) -> DeleteReport` — items are dicts with `"path"` and `"size"` keys (scanner output shape). Raises `UnknownCategoryError` / `UserSelectionRequired`.
  - `UserSelectionRequired(Exception)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deleter.py`:

```python
from pathlib import Path

import pytest

import core.deleter as deleter_mod
from core.deleter import DeleteReport, Outcome, UserSelectionRequired, safe_delete
from core.registry import UnknownCategoryError


@pytest.fixture(autouse=True)
def no_live_process_lookup(monkeypatch):
    monkeypatch.setattr(deleter_mod, "running_apps", lambda: {})


@pytest.fixture
def fake_trash(monkeypatch, tmp_path):
    """Redirect trash_item to move files into a fake .Trash and return that path."""
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir()

    def _fake(path: Path) -> Path:
        dest = trash_dir / path.name
        path.rename(dest)
        return dest

    monkeypatch.setattr(deleter_mod, "trash_item", _fake)
    return trash_dir


def _items(*paths):
    return [{"path": str(p), "size": p.stat().st_size if p.exists() else 0} for p in paths]


def test_unknown_category_refuses(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(UnknownCategoryError):
        safe_delete(_items(f), "not_a_category")


def test_user_data_requires_tripwire(tmp_path):
    f = tmp_path / "backup"
    f.mkdir()
    with pytest.raises(UserSelectionRequired):
        safe_delete([{"path": str(f), "size": 10}], "ios_backups")
    # with the flag it proceeds (dry run so nothing is touched)
    report = safe_delete([{"path": str(f), "size": 10}], "ios_backups",
                         dry_run=True, user_selected=True)
    assert report.trashed_bytes == 10


def test_dry_run_touches_nothing(tmp_path):
    f = tmp_path / "cache.dat"
    f.write_bytes(b"12345")
    report = safe_delete(_items(f), "caches", dry_run=True)
    assert f.exists()
    assert report.dry_run
    assert len(report.trashed) == 1
    assert report.trashed_bytes == 5
    assert report.trashed[0].trash_path == ""


def test_real_delete_goes_to_trash(tmp_path, fake_trash):
    f = tmp_path / "cache.dat"
    f.write_bytes(b"12345")
    report = safe_delete(_items(f), "caches")
    assert not f.exists()
    assert (fake_trash / "cache.dat").exists()
    assert report.trashed[0].trash_path == str(fake_trash / "cache.dat")
    assert report.trashed_bytes == 5


def test_protected_paths_skipped_with_reason(tmp_path, fake_trash):
    target = Path.home() / "Documents"
    link = tmp_path / "sneaky"
    link.symlink_to(target)
    report = safe_delete([{"path": str(link), "size": 1}], "caches")
    assert len(report.skipped) == 1
    assert report.skipped[0].reason
    assert len(report.trashed) == 0


def test_in_use_skip_names_the_app(tmp_path, monkeypatch, fake_trash):
    monkeypatch.setattr(deleter_mod, "running_apps",
                        lambda: {"com.example.app": "Example"})
    cache = Path.home() / "Library" / "Caches" / "com.example.app"
    report = safe_delete([{"path": str(cache), "size": 1}], "caches", dry_run=True)
    assert report.skipped[0].reason == "Example is running"


def test_vanished_file_is_skipped(tmp_path, fake_trash):
    report = safe_delete([{"path": str(tmp_path / "gone.txt"), "size": 3}], "caches")
    assert len(report.skipped) == 1
    assert "no longer exists" in report.skipped[0].reason


def test_failure_is_reported_not_raised(tmp_path, monkeypatch):
    def _boom(path):
        raise deleter_mod.TrashError("disk full")
    monkeypatch.setattr(deleter_mod, "trash_item", _boom)
    f = tmp_path / "cache.dat"
    f.write_bytes(b"123")
    report = safe_delete(_items(f), "caches")
    assert len(report.failed) == 1
    assert "disk full" in report.failed[0].reason
    assert f.exists()  # never permanently deleted on failure


def test_report_math_adds_up(tmp_path, fake_trash):
    a = tmp_path / "a.txt"; a.write_bytes(b"11")
    b = tmp_path / "b.txt"; b.write_bytes(b"222")
    gone = tmp_path / "gone.txt"
    items = _items(a, b) + [{"path": str(gone), "size": 9}]
    report = safe_delete(items, "caches")
    assert len(report.results) == 3
    assert len(report.trashed) == 2
    assert len(report.skipped) == 1
    assert report.trashed_bytes == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_deleter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.deleter'`

- [ ] **Step 3: Implement the deleter**

Create `core/deleter.py`:

```python
"""safe_delete() - the only function in this codebase allowed to destroy file data."""
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from core.registry import get as get_category
from core.safety import is_protected, running_apps
from core.trash import TrashError, trash_item
from utils.logger import log_cleaning_action


class Outcome(str, Enum):
    TRASHED = "trashed"
    SKIPPED = "skipped"
    FAILED = "failed"


class UserSelectionRequired(Exception):
    """A user_data category was passed without user_selected=True."""


@dataclass
class PathResult:
    path: str
    outcome: Outcome
    size: int = 0
    reason: str = ""       # skip reason or failure message
    trash_path: str = ""   # set for real (non-dry-run) trashed items


@dataclass
class DeleteReport:
    category: str
    dry_run: bool
    results: list[PathResult] = field(default_factory=list)

    def _with(self, outcome: Outcome) -> list[PathResult]:
        return [r for r in self.results if r.outcome is outcome]

    @property
    def trashed(self) -> list[PathResult]:
        return self._with(Outcome.TRASHED)

    @property
    def skipped(self) -> list[PathResult]:
        return self._with(Outcome.SKIPPED)

    @property
    def failed(self) -> list[PathResult]:
        return self._with(Outcome.FAILED)

    @property
    def trashed_bytes(self) -> int:
        return sum(r.size for r in self.trashed)


def safe_delete(items: list[dict], category: str,
                dry_run: bool = False, user_selected: bool = False) -> DeleteReport:
    """Move items to the Trash after safety checks.

    items: dicts with "path" (str) and "size" (int, scanner's estimate).
    Raises UnknownCategoryError for unregistered categories and
    UserSelectionRequired when a user_data category lacks the tripwire flag.
    """
    cat = get_category(category)
    if cat.user_data and not user_selected:
        raise UserSelectionRequired(
            f"'{category}' contains user data; items must be individually selected "
            f"and passed with user_selected=True."
        )

    running = running_apps()
    report = DeleteReport(category=category, dry_run=dry_run)

    for item in items:
        path_str = item["path"]
        size = int(item.get("size", 0))
        path = Path(path_str)

        protected, reason = is_protected(path, running)
        if protected:
            report.results.append(PathResult(path_str, Outcome.SKIPPED, size, reason))
            continue

        if dry_run:
            log_cleaning_action("Would Trash", path_str, dry_run=True)
            report.results.append(PathResult(path_str, Outcome.TRASHED, size))
            continue

        if not path.exists() and not path.is_symlink():
            report.results.append(
                PathResult(path_str, Outcome.SKIPPED, size, "no longer exists"))
            continue

        try:
            trash_path = trash_item(path)
            log_cleaning_action("Trashed", path_str)
            report.results.append(
                PathResult(path_str, Outcome.TRASHED, size, trash_path=str(trash_path)))
        except (TrashError, OSError) as e:
            log_cleaning_action("Failed to Trash", f"{path_str} ({e})")
            report.results.append(PathResult(path_str, Outcome.FAILED, size, str(e)))

    return report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_deleter.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add core/deleter.py tests/test_deleter.py
git commit -m "feat: safe_delete engine - registry check, tripwire, skips with reasons"
```

---

### Task 6: Surgical empty (`core/deleter.py::reclaim`)

**Files:**
- Modify: `core/deleter.py` (append)
- Test: `tests/test_deleter.py` (append)

**Interfaces:**
- Produces: `ReclaimReport(deleted: int, failed: int, freed_bytes: int)` and `reclaim(reports: list[DeleteReport]) -> ReclaimReport` — permanently deletes exactly the `trash_path`s recorded in the given reports; ignores dry-run reports; never touches anything else in the Trash.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_deleter.py`:

```python
from core.deleter import ReclaimReport, reclaim


def test_reclaim_deletes_only_our_items(tmp_path, fake_trash):
    ours = tmp_path / "ours.txt"; ours.write_bytes(b"1234")
    theirs = fake_trash / "users-own-trashed-file.txt"
    theirs.write_text("user put this in the Trash last week")

    report = safe_delete(_items(ours), "caches")
    result = reclaim([report])

    assert isinstance(result, ReclaimReport)
    assert result.deleted == 1
    assert result.freed_bytes == 4
    assert not (fake_trash / "ours.txt").exists()
    assert theirs.exists()  # the rest of the Trash is untouched


def test_reclaim_ignores_dry_run_reports(tmp_path):
    f = tmp_path / "f.txt"; f.write_bytes(b"12")
    report = safe_delete(_items(f), "caches", dry_run=True)
    result = reclaim([report])
    assert result.deleted == 0
    assert f.exists()


def test_reclaim_counts_failures(tmp_path, fake_trash):
    f = tmp_path / "f.txt"; f.write_bytes(b"12")
    report = safe_delete(_items(f), "caches")
    (fake_trash / "f.txt").unlink()  # someone emptied the Trash already
    result = reclaim([report])
    assert result.deleted == 0
    # already-gone items are not failures; nothing to delete
    assert result.failed == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_deleter.py -v -k reclaim`
Expected: FAIL with `ImportError: cannot import name 'ReclaimReport'`

- [ ] **Step 3: Implement reclaim**

Append to `core/deleter.py`:

```python
from core.trash import NotInTrashError, delete_from_trash  # noqa: E402  (keep at top in practice)


@dataclass
class ReclaimReport:
    deleted: int = 0
    failed: int = 0
    freed_bytes: int = 0


def reclaim(reports: list["DeleteReport"]) -> ReclaimReport:
    """Permanently delete ONLY the items these reports moved to the Trash.

    This is the app's Irreversible 'empty now' step (typed confirmation happens
    in the UI before calling this). Items already gone are silently fine.
    """
    result = ReclaimReport()
    for report in reports:
        if report.dry_run:
            continue
        for r in report.trashed:
            if not r.trash_path:
                continue
            trash_path = Path(r.trash_path)
            if not trash_path.exists() and not trash_path.is_symlink():
                continue
            try:
                delete_from_trash(trash_path)
                log_cleaning_action("Reclaimed", r.path)
                result.deleted += 1
                result.freed_bytes += r.size
            except (NotInTrashError, OSError) as e:
                log_cleaning_action("Failed to Reclaim", f"{r.path} ({e})")
                result.failed += 1
    return result
```

(Move the `from core.trash import ...` line up to the existing import block at the top of the file.)

- [ ] **Step 4: Run the deleter suite**

Run: `python3 -m pytest tests/test_deleter.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add core/deleter.py tests/test_deleter.py
git commit -m "feat: surgical reclaim - permanently delete only what the app trashed"
```

---

### Task 7: Junk-only scan_all; Space Finder scanners

**Files:**
- Modify: `scanner/system_data.py`
- Test: `tests/test_system_data.py` (modify scanner-related parts)

**Interfaces:**
- Produces: `scan_all(min_cache_age=7, min_log_age=30) -> list[ScanResult]` returning ONLY `caches`, `logs`, `temp` (Junk). `scan_downloads() -> ScanResult` (category `downloads`, NO age filter, age recorded per item). `scan_ios_backups()` unchanged. `scan_space_finder() -> list[ScanResult]` returning non-empty results of `[scan_downloads(), scan_ios_backups()]`.
- `scan_download_old` is deleted (its 90-day cutoff treated downloads as junk — rejected in grilling decision 3).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_system_data.py`:

```python
from scanner.system_data import scan_all, scan_downloads, scan_space_finder


def test_scan_all_returns_only_junk_categories(monkeypatch, tmp_path):
    # scan_all must never return user-data categories
    results = scan_all()
    categories = {r.category for r in results}
    assert categories <= {"caches", "logs", "temp"}


def test_scan_downloads_has_no_age_filter(monkeypatch, tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    fresh = downloads / "yesterday.pdf"
    fresh.write_bytes(b"x" * 10)
    monkeypatch.setattr("scanner.system_data.HOME", tmp_path)
    result = scan_downloads()
    assert result.category == "downloads"
    paths = [f["path"] for f in result.files]
    assert str(fresh) in paths  # brand-new file IS listed; age is a signal, not a filter


def test_scan_space_finder_categories(monkeypatch, tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "f.bin").write_bytes(b"x")
    monkeypatch.setattr("scanner.system_data.HOME", tmp_path)
    results = scan_space_finder()
    assert {r.category for r in results} <= {"downloads", "ios_backups"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_system_data.py -v -k "junk or downloads or space_finder"`
Expected: FAIL with `ImportError: cannot import name 'scan_downloads'`

- [ ] **Step 3: Implement the split**

In `scanner/system_data.py`:

1. Rename `scan_download_old(min_age_days=90)` to `scan_downloads()` and remove the age filter (keep recording `age` per file — it becomes a UI signal):

```python
def scan_downloads() -> ScanResult:
    """Scan Downloads folder. User data: everything is listed; age is a signal only."""
    result = ScanResult("downloads", "Downloads")
    downloads = HOME / "Downloads"
    if not downloads.exists():
        return result
    try:
        for item in downloads.iterdir():
            if item.name in EXCLUDED:
                continue
            try:
                age = file_age_days(item)
                size = get_dir_size(item) if item.is_dir() else item.stat().st_size
                result.add_file(str(item), size, age)
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError):
        pass
    return result
```

2. Replace `scan_all` (drop `min_download_age` param):

```python
def scan_all(min_cache_age: int = 7, min_log_age: int = 30) -> list[ScanResult]:
    """Run all Junk scans. Never returns user-data categories (see /CONTEXT.md)."""
    results = [
        scan_caches(min_cache_age),
        scan_logs(min_log_age),
        scan_temp_files(),
    ]
    return [r for r in results if r.file_count > 0]


def scan_space_finder() -> list[ScanResult]:
    """Reclaimable User Data: browse-and-pick only, never bulk-cleaned."""
    results = [scan_downloads(), scan_ios_backups()]
    return [r for r in results if r.file_count > 0]
```

3. Fix any existing test in `tests/test_system_data.py` that references `scan_download_old` or asserts downloads/ios_backups appear in `scan_all` — update those tests to the new functions (`scan_downloads`, `scan_space_finder`).

- [ ] **Step 4: Run the file's tests**

Run: `python3 -m pytest tests/test_system_data.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add scanner/system_data.py tests/test_system_data.py
git commit -m "feat: split Junk (scan_all) from Reclaimable User Data (scan_space_finder)"
```

---

### Task 8: Refactor `cleaner/system_data.py` onto safe_delete

**Files:**
- Modify: `cleaner/system_data.py` (full rewrite, it shrinks)
- Test: `tests/test_system_data.py` (rewrite the clean_system_data test)

**Interfaces:**
- Produces: `clean_system_data(dry_run=False) -> dict[str, DeleteReport]` keyed by category key (`caches`, `logs`, `temp`); `clean_files(scan_result, dry_run=False) -> DeleteReport` (delegates to safe_delete with `scan_result.category`).
- Consumes: `safe_delete(items, category, dry_run)` from Task 5, `scan_all()` from Task 7.

- [ ] **Step 1: Rewrite the cleaner test**

In `tests/test_system_data.py`, replace `test_system_data_scan_and_clean` (and its send2trash mocking, lines ~23-93) with:

```python
import core.deleter as deleter_mod
from cleaner.system_data import clean_files, clean_system_data
from scanner.system_data import ScanResult


def _fake_trash_fixture(monkeypatch, tmp_path):
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir(exist_ok=True)

    def _fake(path):
        dest = trash_dir / path.name
        path.rename(dest)
        return dest

    monkeypatch.setattr(deleter_mod, "trash_item", _fake)
    monkeypatch.setattr(deleter_mod, "running_apps", lambda: {})
    return trash_dir


def test_clean_files_delegates_to_safe_delete(tmp_path, monkeypatch):
    trash_dir = _fake_trash_fixture(monkeypatch, tmp_path)
    f = tmp_path / "old.cache"
    f.write_bytes(b"12345")
    sr = ScanResult("caches", "User Caches")
    sr.add_file(str(f), 5, 30)

    report_dry = clean_files(sr, dry_run=True)
    assert f.exists()
    assert report_dry.trashed_bytes == 5

    report = clean_files(sr, dry_run=False)
    assert not f.exists()
    assert (trash_dir / "old.cache").exists()
    assert report.trashed_bytes == 5


def test_clean_system_data_returns_reports_by_category(monkeypatch, tmp_path):
    _fake_trash_fixture(monkeypatch, tmp_path)
    sr = ScanResult("caches", "User Caches")
    monkeypatch.setattr("cleaner.system_data.scan_all", lambda: [sr])
    result = clean_system_data(dry_run=True)
    assert set(result.keys()) == {"caches"}
    from core.deleter import DeleteReport
    assert isinstance(result["caches"], DeleteReport)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_system_data.py -v`
Expected: FAIL (`clean_files` still returns the old dict shape)

- [ ] **Step 3: Rewrite the cleaner**

Replace the full contents of `cleaner/system_data.py`:

```python
"""System data cleaner - Junk only. All deletion goes through core.deleter."""
from core.deleter import DeleteReport, safe_delete
from scanner.system_data import ScanResult, scan_all


def clean_files(scan_result: ScanResult, dry_run: bool = False) -> DeleteReport:
    """Trash everything a Junk scan found. Safety checks live in safe_delete."""
    return safe_delete(scan_result.files, scan_result.category, dry_run=dry_run)


def clean_system_data(dry_run: bool = False) -> dict[str, DeleteReport]:
    """Scan and clean all Junk categories. Returns reports keyed by category."""
    return {
        result.category: clean_files(result, dry_run=dry_run)
        for result in scan_all()
    }
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_system_data.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add cleaner/system_data.py tests/test_system_data.py
git commit -m "refactor: system_data cleaner delegates to safe_delete"
```

---

### Task 9: Refactor `cleaner/privacy.py`; separate recents

**Files:**
- Modify: `cleaner/privacy.py` (full rewrite)
- Test: `tests/test_privacy.py` (rewrite cleaning tests)

**Interfaces:**
- Produces: `clean_browser_data(dry_run=False) -> DeleteReport` (category `browser_cache`; only `type == "caches"` items, as today), `clean_tracking_data(dry_run=False) -> DeleteReport` (category `tracking_data`; keeps the ByHost exclusion), `clean_privacy(dry_run=False) -> dict[str, DeleteReport]` (browser + tracking ONLY — recents is no longer bundled), `clear_recently_used(dry_run=False) -> dict` (unchanged mechanism; UI gates it as an Irreversible Action).

- [ ] **Step 1: Rewrite the privacy tests**

Replace the cleaning half of `tests/test_privacy.py` (keep any pure-scanner tests) with:

```python
import core.deleter as deleter_mod
from core.deleter import DeleteReport
from cleaner.privacy import clean_privacy, clean_browser_data, clear_recently_used


def test_clean_privacy_excludes_recents(monkeypatch, tmp_path):
    monkeypatch.setattr("cleaner.privacy.scan_browser_data", lambda: [])
    monkeypatch.setattr("cleaner.privacy.scan_tracking_data", lambda: [])
    result = clean_privacy(dry_run=True)
    assert set(result.keys()) == {"browser_cache", "tracking_data"}
    assert all(isinstance(r, DeleteReport) for r in result.values())


def test_clean_browser_data_only_caches(monkeypatch, tmp_path):
    monkeypatch.setattr(deleter_mod, "running_apps", lambda: {})
    cache_dir = tmp_path / "BrowserCache"
    cache_dir.mkdir()
    history = tmp_path / "History.db"
    history.write_text("history")
    monkeypatch.setattr("cleaner.privacy.scan_browser_data", lambda: [
        {"browser": "TestBrowser", "type": "caches", "path": str(cache_dir), "size": 100},
        {"browser": "TestBrowser", "type": "history", "path": str(history), "size": 50},
    ])
    report = clean_browser_data(dry_run=True)
    paths = [r.path for r in report.results]
    assert str(cache_dir) in paths
    assert str(history) not in paths  # history is never cleaned by this function


def test_clear_recently_used_dry_run(monkeypatch, tmp_path):
    recents = tmp_path / "com.apple.recentitems"
    recents.write_text("data")
    monkeypatch.setattr("cleaner.privacy.scan_recently_used",
                        lambda: [{"type": "recent_items", "path": str(recents), "size": 4}])
    stats = clear_recently_used(dry_run=True)
    assert stats["cleared"] == 1
    assert recents.read_text() == "data"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_privacy.py -v`
Expected: FAIL (old return shapes)

- [ ] **Step 3: Rewrite the cleaner**

Replace the full contents of `cleaner/privacy.py`:

```python
"""Privacy cleaner. Trash-able categories go through core.deleter; recents-clear
is an Irreversible Action (in-place rewrite) gated by the UI."""
from pathlib import Path

from core.deleter import DeleteReport, safe_delete
from scanner.privacy import scan_browser_data, scan_recently_used, scan_tracking_data
from utils.logger import log_cleaning_action


def clean_browser_data(dry_run: bool = False) -> DeleteReport:
    """Trash browser caches only (history is scanned for display, never cleaned here)."""
    items = [i for i in scan_browser_data() if i["type"] == "caches"]
    return safe_delete(items, "browser_cache", dry_run=dry_run)


def clean_tracking_data(dry_run: bool = False) -> DeleteReport:
    items = [i for i in scan_tracking_data()
             if "Preferences/ByHost" not in i["path"]]
    return safe_delete(items, "tracking_data", dry_run=dry_run)


def clean_privacy(dry_run: bool = False) -> dict[str, DeleteReport]:
    """Trash-able privacy categories. Recents is NOT included - it is an
    Irreversible Action the UI must gate and invoke separately."""
    return {
        "browser_cache": clean_browser_data(dry_run=dry_run),
        "tracking_data": clean_tracking_data(dry_run=dry_run),
    }


def clear_recently_used(dry_run: bool = False) -> dict:
    """Irreversible Action (registry: 'recents'): rewrites files in place."""
    stats = {"cleared": 0, "failed": 0}
    for item in scan_recently_used():
        path = Path(item["path"])
        try:
            if dry_run:
                stats["cleared"] += 1
                log_cleaning_action("Would Clear", str(path), dry_run=True)
                continue
            if path.is_file():
                path.write_text("")
                log_cleaning_action("Cleared", str(path))
            stats["cleared"] += 1
        except (OSError, PermissionError) as e:
            stats["failed"] += 1
            log_cleaning_action("Failed to Clear", f"{path} ({e})")
    return stats
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_privacy.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add cleaner/privacy.py tests/test_privacy.py
git commit -m "refactor: privacy cleaner via safe_delete; recents split out as Irreversible"
```

---

### Task 10: Refactor `cleaner/app_remnants.py`

**Files:**
- Modify: `cleaner/app_remnants.py` (full rewrite)
- Test: `tests/test_app_remnants.py` (rewrite cleaning tests; keep scanner tests)

**Interfaces:**
- Produces: `clean_leftovers(app_name, dry_run=False) -> DeleteReport` (category `app_leftovers`), `uninstall_app(app_name, dry_run=False) -> dict` with keys `"app": DeleteReport` (category `app_bundle`) and `"leftovers": DeleteReport`.

- [ ] **Step 1: Rewrite the cleaning tests**

In `tests/test_app_remnants.py`, replace the send2trash-mocking test (`test_find_leftovers_and_uninstall` cleaning half) with:

```python
import core.deleter as deleter_mod
from core.deleter import DeleteReport
from cleaner.app_remnants import clean_leftovers, uninstall_app


def _fake_trash(monkeypatch, tmp_path):
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir(exist_ok=True)

    def _fake(path):
        dest = trash_dir / path.name
        path.rename(dest)
        return dest

    monkeypatch.setattr(deleter_mod, "trash_item", _fake)
    monkeypatch.setattr(deleter_mod, "running_apps", lambda: {})
    return trash_dir


def test_clean_leftovers_reports(tmp_path, monkeypatch):
    _fake_trash(monkeypatch, tmp_path)
    leftover = tmp_path / "com.testapp.plist"
    leftover.write_text("x")
    monkeypatch.setattr("cleaner.app_remnants.find_leftovers",
                        lambda name: [{"path": str(leftover), "size": 1, "type": "file"}])
    report = clean_leftovers("TestApp", dry_run=False)
    assert isinstance(report, DeleteReport)
    assert report.category == "app_leftovers"
    assert not leftover.exists()


def test_uninstall_app_returns_two_reports(tmp_path, monkeypatch):
    trash_dir = _fake_trash(monkeypatch, tmp_path)
    apps_dir = tmp_path / "Applications"
    apps_dir.mkdir()
    bundle = apps_dir / "TestApp.app"
    bundle.mkdir()
    monkeypatch.setattr("cleaner.app_remnants.APPLICATIONS_DIR", apps_dir)
    monkeypatch.setattr("cleaner.app_remnants.find_leftovers", lambda name: [])

    result = uninstall_app("TestApp", dry_run=False)
    assert isinstance(result["app"], DeleteReport)
    assert result["app"].category == "app_bundle"
    assert len(result["app"].trashed) == 1
    assert not bundle.exists()
    assert (trash_dir / "TestApp.app").exists()
    assert isinstance(result["leftovers"], DeleteReport)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_app_remnants.py -v`
Expected: FAIL (old shapes, no APPLICATIONS_DIR)

- [ ] **Step 3: Rewrite the cleaner**

Replace the full contents of `cleaner/app_remnants.py`:

```python
"""App uninstaller - removes .app bundle + leftovers via core.deleter."""
from pathlib import Path

from core.deleter import DeleteReport, safe_delete
from scanner.app_remnants import find_leftovers
from utils.helpers import get_dir_size

APPLICATIONS_DIR = Path("/Applications")


def clean_leftovers(app_name: str, dry_run: bool = False) -> DeleteReport:
    return safe_delete(find_leftovers(app_name), "app_leftovers", dry_run=dry_run)


def uninstall_app(app_name: str, dry_run: bool = False) -> dict:
    """Trash the .app bundle and its leftovers. Returns {'app': DeleteReport,
    'leftovers': DeleteReport}."""
    bundle = APPLICATIONS_DIR / f"{app_name}.app"
    bundle_items = []
    if bundle.exists():
        bundle_items.append({"path": str(bundle), "size": get_dir_size(bundle)})

    return {
        "app": safe_delete(bundle_items, "app_bundle", dry_run=dry_run),
        "leftovers": clean_leftovers(app_name, dry_run=dry_run),
    }
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_app_remnants.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add cleaner/app_remnants.py tests/test_app_remnants.py
git commit -m "refactor: app uninstaller via safe_delete (app_bundle + app_leftovers)"
```

---

### Task 11: Refactor `cleaner/optimization.py`

**Files:**
- Modify: `cleaner/optimization.py`
- Test: `tests/test_optimization.py` (rewrite cache-clearing tests; keep brew/launch-agent tests)

**Interfaces:**
- Produces: `clear_xcode_derived_data`, `clear_cocoapods_cache`, `clear_pip_cache` each `(dry_run=False) -> DeleteReport | dict` — a `DeleteReport` (categories `xcode_derived_data`, `cocoapods_cache`, `pip_cache`) when the path exists, else the existing `{"message": ..., "skipped": True}` dict. `run_brew_cleanup` / `clear_npm_cache` unchanged (external tools, `via_trash=False`). `optimize_mac(dry_run=False) -> dict` same keys as today; values are DeleteReports or dicts.

- [ ] **Step 1: Rewrite the cache-clearing tests**

In `tests/test_optimization.py`, replace `test_clear_caches` (the send2trash-mocking one) with:

```python
import core.deleter as deleter_mod
from core.deleter import DeleteReport
from cleaner.optimization import clear_pip_cache


def test_clear_pip_cache_via_safe_delete(tmp_path, monkeypatch):
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir()

    def _fake(path):
        dest = trash_dir / path.name
        path.rename(dest)
        return dest

    monkeypatch.setattr(deleter_mod, "trash_item", _fake)
    monkeypatch.setattr(deleter_mod, "running_apps", lambda: {})

    pip_cache = tmp_path / "pip"
    pip_cache.mkdir()
    (pip_cache / "wheel.whl").write_bytes(b"x" * 10)
    monkeypatch.setattr("cleaner.optimization.PIP_CACHE", pip_cache)

    report = clear_pip_cache(dry_run=False)
    assert isinstance(report, DeleteReport)
    assert report.category == "pip_cache"
    assert not pip_cache.exists()


def test_clear_pip_cache_missing_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr("cleaner.optimization.PIP_CACHE", tmp_path / "nope")
    result = clear_pip_cache()
    assert result["skipped"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_optimization.py -v`
Expected: FAIL (no PIP_CACHE symbol; old shapes)

- [ ] **Step 3: Refactor the three via-Trash cache functions**

In `cleaner/optimization.py`: remove `from send2trash import send2trash`; add module-level path constants and rewrite the three functions to one shared helper. Replace `clear_xcode_derived_data`, `clear_cocoapods_cache`, `clear_pip_cache` with:

```python
from core.deleter import DeleteReport, safe_delete
from utils.helpers import get_dir_size

DERIVED_DATA = Path.home() / "Library" / "Developer" / "Xcode" / "DerivedData"
PODS_CACHE = Path.home() / ".cocoapods"
PIP_CACHE = Path.home() / "Library" / "Caches" / "pip"


def _clear_cache_dir(path: Path, category: str, dry_run: bool) -> DeleteReport | dict:
    if not path.exists():
        return {"message": f"No {category} found", "skipped": True}
    items = [{"path": str(path), "size": get_dir_size(path)}]
    return safe_delete(items, category, dry_run=dry_run)


def clear_xcode_derived_data(dry_run: bool = False) -> DeleteReport | dict:
    return _clear_cache_dir(DERIVED_DATA, "xcode_derived_data", dry_run)


def clear_cocoapods_cache(dry_run: bool = False) -> DeleteReport | dict:
    return _clear_cache_dir(PODS_CACHE, "cocoapods_cache", dry_run)


def clear_pip_cache(dry_run: bool = False) -> DeleteReport | dict:
    return _clear_cache_dir(PIP_CACHE, "pip_cache", dry_run)
```

`run_brew_cleanup`, `clear_npm_cache`, `run_periodic_scripts`, `optimize_mac` stay as they are (brew/npm are `via_trash=False` external tools — the UI labels them).

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_optimization.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add cleaner/optimization.py tests/test_optimization.py
git commit -m "refactor: dev-cache clearing via safe_delete; brew/npm stay external"
```

---

### Task 12: Snapshot Reclaimed measurement

**Files:**
- Modify: `cleaner/snapshots.py` (only `clean_snapshots`)
- Test: `tests/test_snapshots.py` (extend)

**Interfaces:**
- Produces: `clean_snapshots(dry_run=False) -> dict` — real runs gain `"reclaimed_bytes": int` measured as the disk-free delta around deletion (tmutil reports nothing itself; clamped at ≥ 0).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_snapshots.py`:

```python
def test_clean_snapshots_reports_reclaimed_bytes(monkeypatch):
    monkeypatch.setattr("cleaner.snapshots.list_snapshots",
                        lambda: [{"name": "com.apple.TimeMachine.2026-07-01-120000.local"}])
    monkeypatch.setattr("cleaner.snapshots.delete_all_snapshots",
                        lambda: (["Deleted snapshot: x"], []))
    frees = iter([100_000, 100_500])  # before, after

    class FakeUsage:
        def __init__(self, free):
            self.free = free

    monkeypatch.setattr("cleaner.snapshots.shutil.disk_usage",
                        lambda _: FakeUsage(next(frees)))
    result = clean_snapshots(dry_run=False)
    assert result["reclaimed_bytes"] == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_snapshots.py -v -k reclaimed`
Expected: FAIL with `KeyError: 'reclaimed_bytes'` (or missing shutil attr)

- [ ] **Step 3: Implement**

In `cleaner/snapshots.py`, add `import shutil` at the top, and in `clean_snapshots` replace the real-run branch:

```python
    free_before = shutil.disk_usage("/").free
    successes, failures = delete_all_snapshots()
    free_after = shutil.disk_usage("/").free
    return {
        "deleted": len(successes),
        "failed": len(failures),
        "successes": successes,
        "failures": failures,
        "reclaimed_bytes": max(0, free_after - free_before),
    }
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_snapshots.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add cleaner/snapshots.py tests/test_snapshots.py
git commit -m "feat: snapshots report reclaimed_bytes via disk-free delta"
```

---

### Task 13: Remove the old safety path

**Files:**
- Modify: `utils/helpers.py` (delete `is_safe_to_delete`)
- Modify: `tests/test_helpers.py` (drop its import + test)
- Modify: `requirements.txt` (drop send2trash)

**Interfaces:**
- Consumes: nothing — by now no production module imports `is_safe_to_delete` or `send2trash` (Tasks 8-11 removed the callers).

- [ ] **Step 1: Verify no remaining callers**

Run: `grep -rn "is_safe_to_delete\|send2trash" --include="*.py" cleaner/ scanner/ utils/ core/ main.py`
Expected: only the `utils/helpers.py` definition (and its import in tests). If anything else appears, STOP — a previous task missed a caller.

- [ ] **Step 2: Delete the function and its test**

- In `utils/helpers.py`: delete the entire `is_safe_to_delete` function.
- In `tests/test_helpers.py`: remove `is_safe_to_delete` from the import list and delete any test exercising it.

- [ ] **Step 3: Drop send2trash from requirements.txt**

Replace the full contents of `requirements.txt` with:

```
rich>=13.7.0
pyobjc-framework-Cocoa>=10.0
pytest>=8.0.0
```

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest tests/ -v`
Expected: everything passes

- [ ] **Step 5: Commit**

```bash
git add utils/helpers.py tests/test_helpers.py requirements.txt
git commit -m "chore: remove legacy is_safe_to_delete and send2trash dependency"
```

---

### Task 14: Minimal truthful UI wiring (`main.py`)

No visual polish — wording, gates, skip reasons, Space Finder pick-list only. The Textual phase inherits this behavior.

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes: `core.registry.get`/`Level`, `core.deleter.DeleteReport`/`reclaim`, `cleaner.*` new return shapes (Tasks 8-12), `scanner.system_data.scan_space_finder`.

- [ ] **Step 1: Add shared UI helpers**

In `main.py`, add imports and three helpers after `console = Console()`:

```python
from core import registry
from core.deleter import DeleteReport, reclaim
from scanner.system_data import scan_space_finder

LEVEL_STYLES = {"SAFE": "green", "CAUTION": "yellow", "RISKY": "red"}


def print_category_header(key: str):
    """Level + plain-English explanation, shown before a category's items."""
    cat = registry.get(key)
    style = LEVEL_STYLES[cat.level.value]
    label = f"[{style}]\\[{cat.level.value}][/{style}]"
    suffix = " [dim](cleared directly - not recoverable via Trash)[/dim]" if not cat.via_trash else ""
    console.print(f"{label} {cat.explanation}{suffix}")


def show_delete_report(report: DeleteReport):
    """Truthful summary: Trashed (not 'freed'), skips with reasons, failures."""
    verb = "Would move to Trash" if report.dry_run else "Moved to Trash"
    console.print(f"  [green]{verb}:[/green] {len(report.trashed)} items "
                  f"(~{format_size(report.trashed_bytes)})")
    for r in report.skipped:
        console.print(f"  [yellow]Skipped:[/yellow] {r.path[-60:]} - {r.reason}")
    for r in report.failed:
        console.print(f"  [red]Failed:[/red] {r.path[-60:]} - {r.reason}")


def confirm_irreversible(what: str) -> bool:
    """Typed gate for Irreversible Actions. Returns True only on literal 'yes'."""
    console.print(f"\n[bold red]{what} cannot be undone.[/bold red]")
    answer = Prompt.ask("Type 'yes' to proceed", default="no")
    return answer.strip().lower() == "yes"


def offer_reclaim(reports: list[DeleteReport]):
    """After a real clean: offer surgical empty of exactly what we trashed."""
    real = [r for r in reports if not r.dry_run]
    total = sum(r.trashed_bytes for r in real)
    if not total:
        return
    console.print(f"\n[bold]~{format_size(total)} moved to Trash[/bold] "
                  f"- recoverable until emptied.")
    if confirm_irreversible(f"Permanently deleting these items to reclaim ~{format_size(total)}"):
        result = reclaim(real)
        console.print(f"[green]Reclaimed ~{format_size(result.freed_bytes)} "
                      f"({result.deleted} items)[/green]")
        if result.failed:
            console.print(f"[red]Failed to reclaim {result.failed} items[/red]")
    else:
        console.print("[dim]Kept in Trash - recover anytime with Put Back.[/dim]")
```

- [ ] **Step 2: Rewire `run_system_data_scan`**

Replace its cleanup section (after the dry_run choice) with:

```python
    dry_run = choice == "1"
    label = "[yellow]DRY RUN[/yellow] - " if dry_run else ""

    console.print(f"\n{label}[bold]Cleaning system data...[/bold]")
    cleanup = clean_system_data(dry_run=dry_run)

    reports = []
    for category, report in cleanup.items():
        print_category_header(category)
        show_delete_report(report)
        reports.append(report)

    total = sum(r.trashed_bytes for r in reports)
    verb = "would be moved to Trash" if dry_run else "moved to Trash"
    console.print(f"\n[bold]Total: ~{format_size(total)} {verb}[/bold]")
    offer_reclaim(reports)
```

- [ ] **Step 3: Rewire `run_privacy_scan` and gate recents**

Replace its cleanup section with:

```python
    dry_run = choice == "1"
    label = "[yellow]DRY RUN[/yellow] - " if dry_run else ""

    console.print(f"\n{label}[bold]Cleaning privacy data...[/bold]")
    result = clean_privacy(dry_run=dry_run)
    reports = []
    for category, report in result.items():
        print_category_header(category)
        show_delete_report(report)
        reports.append(report)
    offer_reclaim(reports)

    # Recents: Irreversible Action, gated separately
    print_category_header("recents")
    if dry_run:
        stats = clear_recently_used(dry_run=True)
        console.print(f"  Would clear {stats['cleared']} recent-items list(s)")
    elif confirm_irreversible("Clearing the recently-used list"):
        stats = clear_recently_used(dry_run=False)
        console.print(f"  [green]Cleared {stats['cleared']} recent-items list(s)[/green]")
```

Add `clear_recently_used` to the `from cleaner.privacy import ...` line.

- [ ] **Step 4: Gate snapshots in `run_snapshots`**

In `run_snapshots`, before calling `clean_snapshots(dry_run=False)` (i.e. when `dry_run` is False), require the gate:

```python
    if not dry_run:
        print_category_header("snapshots")
        if not confirm_irreversible(f"Deleting {len(snapshots)} snapshot(s)"):
            return

    console.print(f"\n{label}[bold]Deleting snapshots...[/bold]")
    result = clean_snapshots(dry_run=dry_run)
    if dry_run:
        console.print(f"[yellow]Would delete {result.get('count', 0)} snapshot(s)[/yellow]")
    else:
        console.print(f"[green]Deleted: {result.get('deleted', 0)} - "
                      f"Reclaimed ~{format_size(result.get('reclaimed_bytes', 0))}[/green]")
        if result.get("failed"):
            console.print(f"[red]Failed: {result.get('failed', 0)}[/red]")
```

- [ ] **Step 5: Rewire `run_app_uninstaller` and `run_optimization` to the new shapes**

`run_app_uninstaller` result section becomes:

```python
    from cleaner.app_remnants import uninstall_app
    console.print(f"\n{label}[bold]Uninstalling {app_name}...[/bold]")
    result = uninstall_app(app_name, dry_run=dry_run)
    for key in ("app", "leftovers"):
        report = result[key]
        print_category_header(report.category)
        show_delete_report(report)
    offer_reclaim([result["app"], result["leftovers"]])
```

`run_optimization` result loop becomes:

```python
    result = optimize_mac(dry_run=dry_run)
    reports = []
    for task, output in result.items():
        if task == "launch_agents":
            continue
        if isinstance(output, DeleteReport):
            print_category_header(output.category)
            show_delete_report(output)
            reports.append(output)
        elif output.get("skipped"):
            console.print(f"  [dim]SKIP[/dim] {task}")
        else:
            print_category_header(task if task in registry.REGISTRY else "brew_cleanup")
            console.print(f"  [green]OK[/green] {task}: {output.get('message', 'Done')}")
    offer_reclaim(reports)
```

- [ ] **Step 6: Add the Space Finder menu**

In `show_main_menu`, add before the quit line:

```python
    console.print("  [9] Space Finder         [Old downloads, iOS backups - pick individually]")
```

Add the handler function:

```python
def run_space_finder():
    """Reclaimable User Data: browse -> pick individual items -> confirm."""
    console.print("\n[bold cyan]Scanning reclaimable user data...[/bold cyan]")
    results = scan_space_finder()
    if not results:
        console.print("[green]Nothing found[/green]")
        return

    # Flat numbered list across categories
    flat = []  # (index, category, file_dict)
    for r in results:
        print_category_header(r.category)
        table = Table(box=box.ROUNDED, title=f"{r.name} ({r.human_size})")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Age", justify="right", style="yellow")
        table.add_column("Size", justify="right", style="magenta")
        table.add_column("Path", style="cyan")
        for f in r.files:
            flat.append((len(flat) + 1, r.category, f))
            idx, _, _ = flat[-1]
            table.add_row(str(idx), f"{f['age_days']:.0f}d", format_size(f["size"]),
                          f["path"][-60:])
        console.print(table)

    raw = Prompt.ask("\nEnter item numbers to remove (comma-separated), or blank to cancel",
                     default="")
    if not raw.strip():
        return
    try:
        chosen = {int(x) for x in raw.replace(" ", "").split(",") if x}
    except ValueError:
        console.print("[red]Invalid selection[/red]")
        return

    selected: dict[str, list[dict]] = {}
    for idx, category, f in flat:
        if idx in chosen:
            selected.setdefault(category, []).append(f)
    if not selected:
        console.print("[yellow]No valid items selected[/yellow]")
        return

    from core.deleter import safe_delete
    reports = []
    for category, items in selected.items():
        report = safe_delete(items, category, dry_run=False, user_selected=True)
        print_category_header(category)
        show_delete_report(report)
        reports.append(report)
    offer_reclaim(reports)
```

Wire it in `main()`:

```python
        elif choice == "9":
            run_space_finder()
```

- [ ] **Step 7: Fix `run_full_scan` (scan_all no longer returns downloads/ios)**

In `run_full_scan`, after the privacy section, add a hint (system data section already shrank automatically):

```python
    console.print("\n[dim]Downloads and iOS backups moved to Space Finder (option 9)[/dim]")
```

- [ ] **Step 8: Verify by running the app's dry-run paths**

Run: `python3 -m pytest tests/ -v` — everything passes.
Then: `python3 main.py`, and manually:
1. Option 1 → Dry Run: category headers show `[SAFE]` + explanations; totals say "would be moved to Trash"; skips (if any) show reasons.
2. Option 9 → items listed with ages; blank input cancels cleanly.
3. Option 4 → Clean: typed gate appears; typing anything but `yes` aborts.
4. `q` to quit.

Expected: no tracebacks, wording matches CONTEXT.md (no "freed" anywhere except snapshot "Reclaimed").

- [ ] **Step 9: Commit**

```bash
git add main.py
git commit -m "feat: truthful UI wiring - levels, skip reasons, Trashed wording, gates, Space Finder"
```

---

### Task 15: Final verification

- [ ] **Step 1: Full suite**

Run: `python3 -m pytest tests/ -v`
Expected: all tests pass.

- [ ] **Step 2: Grep the invariants**

```bash
# No stray deletion mechanisms outside core/ and the two declared Irreversible modules:
grep -rn "send2trash\|shutil.rmtree\|\.unlink()\|os.remove" --include="*.py" cleaner/ scanner/ utils/ main.py
```

Expected: only `cleaner/snapshots.py` (tmutil path — no rmtree/unlink anyway) and `cleaner/privacy.py`'s `write_text("")` pattern; no rmtree/unlink/send2trash hits at all in cleaners. `grep -rn "freed" main.py` → no user-facing "freed" strings except the snapshot/reclaim wording.

- [ ] **Step 3: End-to-end smoke on the real machine (safe)**

Run `python3 main.py`, run option 1 with **Dry Run**, option 8 (Full Scan), option 9 with blank selection. No writes happen; confirm output shapes.

- [ ] **Step 4: Commit anything outstanding & update README**

Replace `README.md` contents:

```markdown
# mac-cleaner

A macOS system cleaner built around one promise: it never destroys anything
you'd miss. Everything goes through the Trash (recoverable until *you* empty
it), every category explains itself, and irreversible actions require typed
confirmation. See CONTEXT.md for the vocabulary and docs/adr/ for key decisions.

Usage: `python3 main.py`
Tests: `python3 -m pytest tests/`
```

```bash
git add README.md
git commit -m "docs: README reflects safety-core promises"
```
