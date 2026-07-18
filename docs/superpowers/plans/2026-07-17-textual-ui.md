# Textual UI Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace main.py's menu loop with a full-screen Textual app that surfaces the safety core's guarantees, adds Large Files + Duplicates pick flows (with two-tier protection), and lands the perf/hygiene debt from phase 1.

**Architecture:** New `ui/` package: `CleanerApp` + one Screen per feature area + three shared widgets (CategoryHeader, ReportView, gate modals) + thread-workers streaming scan results. The UI computes no safety decisions — everything reads `core.registry`; `safe_delete`/`reclaim` remain the only destructive paths.

**Tech Stack:** Python 3.11, Textual ≥1.0, Rich (transitively), PyObjC, pytest + pytest-asyncio (pilot tests).

**Spec:** `docs/superpowers/specs/2026-07-17-textual-ui-design.md`. **Vocabulary:** `/CONTEXT.md` (binding for user-facing strings — Trashed ≠ Reclaimed, Hard/Soft-Protected, Keep-One Invariant).

## Global Constraints

- `safe_delete` is the only function allowed to destroy file data; `reclaim` the only permanent-delete path; snapshots/recents stay gated Irreversible Actions.
- The UI never hardcodes a level, explanation, or gate decision — always via `core.registry` fields (`level`, `explanation`, `user_data`, `via_trash`, `irreversible`).
- Space Finder selections: nothing pre-selected, NO select-all affordance, `safe_delete(..., user_selected=True)` only with paths taken from live checkbox state.
- Gates: `ConfirmModal` (default No) for trashing user_data selections; `TypedGateModal` (literal `yes`, case-insensitive, default reject) for `irreversible` actions and the reclaim step. Dry runs never gate.
- No scanner/cleaner call on the UI thread — thread workers only; UI updates via `self.app.call_from_thread(...)`.
- Tests: isolated to tmp_path; fake trash + `running_apps -> {}` via the shared conftest fixtures (Task 1); scanner functions monkeypatched in screen tests; never scan the real filesystem, never invoke tmutil/sudo, never touch the real Trash except `tests/test_trash.py`'s existing round-trip.
- Pilot tests are `async def` using `app.run_test()`; pytest-asyncio in auto mode is configured in Task 1.
- Textual APIs in this plan target Textual ≥1.0. If a call doesn't match the installed version, check `python3 -c "import textual; print(textual.__version__)"` and consult the official docs for the installed version rather than guessing; report the substitution in your task report.
- Run tests from repo root: `python3 -m pytest tests/ -q`. Suite currently: 104 passed.

---

### Task 1: Dependencies, conftest fixtures, app shell, packaging test

**Files:**
- Modify: `requirements.txt`, `pytest.ini`, `setup.py`
- Create: `tests/conftest.py`, `ui/app.py`, `tests/test_app_shell.py`, `tests/test_packaging.py`

**Interfaces:**
- Produces: `CleanerApp` (empty shell, later tasks extend), shared fixtures `fake_trash` and `no_running_apps` used by every screen test, pytest-asyncio auto mode.

- [ ] **Step 1: Add dependencies and pytest-asyncio config**

`requirements.txt` becomes:

```
rich>=13.7.0
pyobjc-framework-Cocoa>=10.0
textual>=1.0
pytest>=8.0.0
pytest-asyncio>=0.23
```

Run: `pip3 install "textual>=1.0" "pytest-asyncio>=0.23"`

`pytest.ini` becomes:

```
[pytest]
pythonpath = .
testpaths = tests
asyncio_mode = auto
```

- [ ] **Step 2: Shared fixtures**

Create `tests/conftest.py`:

```python
"""Shared fixtures: fake trash + no running apps, for any test driving safe_delete."""
import pytest

import core.deleter as deleter_mod


@pytest.fixture
def no_running_apps(monkeypatch):
    monkeypatch.setattr(deleter_mod, "running_apps", lambda: {})


@pytest.fixture
def fake_trash(monkeypatch, tmp_path, no_running_apps):
    """Redirect trash_item into a fake .Trash dir; returns that dir."""
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir(exist_ok=True)

    def _fake(path):
        dest = trash_dir / path.name
        path.rename(dest)
        return dest

    monkeypatch.setattr(deleter_mod, "trash_item", _fake)
    return trash_dir
```

Existing test files define their own local versions of these; do NOT refactor them in this task (later tasks may). New tests use the conftest fixtures.

- [ ] **Step 3: Write failing tests (app shell + packaging)**

Create `tests/test_app_shell.py`:

```python
from ui.app import CleanerApp


async def test_app_boots_and_quits():
    app = CleanerApp()
    async with app.run_test() as pilot:
        assert app.title == "Mac Cleaner"
        await pilot.press("q")
    assert app.return_value is None  # exited cleanly
```

Create `tests/test_packaging.py`:

```python
"""py2app manifest must list every top-level package (phase-1 regression: 'core' was missing)."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _setup_packages() -> set[str]:
    text = (ROOT / "setup.py").read_text()
    match = re.search(r"[\"']packages[\"']\s*:\s*(\[[^\]]*\])", text)
    assert match, "packages list not found in setup.py"
    return set(ast.literal_eval(match.group(1)))


def test_setup_packages_covers_all_top_level_packages():
    on_disk = {
        p.parent.name
        for p in ROOT.glob("*/__init__.py")
        if p.parent.name not in {"tests", "dist", "build"}
    }
    missing = on_disk - _setup_packages()
    assert not missing, f"setup.py packages missing: {missing}"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_app_shell.py tests/test_packaging.py -v`
Expected: test_app_shell FAILS (`ModuleNotFoundError: ui.app` — `ui/` is an empty package); test_packaging may pass already (core was added in phase 1) — if it passes, fine.

- [ ] **Step 5: Implement the shell**

Create `ui/app.py`:

```python
"""CleanerApp - the Textual application shell. Screens are added by later tasks."""
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header


class CleanerApp(App):
    TITLE = "Mac Cleaner"
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
```

- [ ] **Step 6: Verify, then full suite**

Run: `python3 -m pytest tests/test_app_shell.py tests/test_packaging.py -v` → all pass.
Run: `python3 -m pytest tests/ -q` → 104 + 2 = 106 passed (no regressions; the asyncio_mode change must not break existing tests).

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini tests/conftest.py ui/app.py tests/test_app_shell.py tests/test_packaging.py setup.py
git commit -m "feat: textual app shell, shared test fixtures, packaging manifest test"
```

(Include setup.py only if you changed it; the packaging test may already pass.)

---

### Task 2: Two-tier protection (Hard vs Soft)

**Files:**
- Modify: `core/safety.py`, `core/deleter.py`, `tests/test_safety.py`, `tests/test_deleter.py`, `tests/test_large_files.py`

**Interfaces:**
- Produces: `is_protected(path, running=None, allow_user_content=False) -> tuple[bool, str]`. `USER_PROTECTED` splits into `HARD_PROTECTED` (Keychains, Mail, `.ssh`, `.gnupg`, iCloud Drive `~/Library/Mobile Documents`) and `SOFT_PROTECTED` (`~/Documents`, `~/Desktop`, `~/Pictures`). The dead `HOME/"Mobile Documents"` entry is dropped. `safe_delete` passes `allow_user_content=(cat.user_data and user_selected)`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_safety.py`, replace `test_user_data_protected`'s parametrize list understanding with the two-tier split — keep that test (all its paths must STILL be protected by default) and ADD:

```python
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
```

In `tests/test_deleter.py`, add:

```python
def test_user_selected_unlocks_soft_protected(tmp_path, monkeypatch, fake_trash):
    # a downloads-category item living under a Soft-Protected dir, dry-run
    doc = Path.home() / "Documents" / "never-created.bin"
    report = safe_delete([{"path": str(doc), "size": 5}], "downloads",
                         dry_run=True, user_selected=True)
    # soft protection yielded: not skipped-as-protected (it's TRASHED in dry-run;
    # nonexistence is only checked on real runs)
    assert len(report.trashed) == 1


def test_junk_categories_never_unlock_soft_protection(tmp_path, fake_trash):
    doc = Path.home() / "Documents" / "never-created.bin"
    report = safe_delete([{"path": str(doc), "size": 5}], "caches", dry_run=True)
    assert len(report.skipped) == 1
```

In `tests/test_large_files.py`, `test_clean_large_files_protected_paths_skipped` currently asserts a `~/Documents` path is skipped — that path is now Soft-Protected and clean_large_files passes user_selected=True, so REPLACE it with:

```python
def test_clean_large_files_hard_protected_still_skipped(monkeypatch, no_running_apps):
    from pathlib import Path as P
    key = P.home() / ".ssh" / "id_ed25519"
    report = clean_large_files([str(key)], dry_run=True)
    assert len(report.skipped) == 1
    assert report.skipped[0].reason
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_safety.py tests/test_deleter.py tests/test_large_files.py -v`
Expected: new tests FAIL (`is_protected` has no `allow_user_content` param).

- [ ] **Step 3: Implement**

In `core/safety.py`, replace `USER_PROTECTED` with:

```python
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
```

Change the signature and tier-2 block of `is_protected`:

```python
def is_protected(path: Path, running: dict[str, str] | None = None,
                 allow_user_content: bool = False) -> tuple[bool, str]:
```

```python
    if _under_any(resolved, HARD_PROTECTED):
        return True, "personal data (protected location)"

    if not allow_user_content and _under_any(resolved, SOFT_PROTECTED):
        return True, "personal data (use Space Finder to remove individually)"
```

(Photos-library / Trash component checks and all tier-0/1 checks stay ABOVE or unaffected — they must never yield; ensure the component loop runs before the owner check as today and does not consult `allow_user_content`.)

In `core/deleter.py::safe_delete`, compute once before the loop and pass through:

```python
    allow_user_content = cat.user_data and user_selected
```
and change the call to:
```python
        protected, reason = is_protected(path, running, allow_user_content)
```

- [ ] **Step 4: Run the three test files, then the full suite**

Run: `python3 -m pytest tests/test_safety.py tests/test_deleter.py tests/test_large_files.py -v` → all pass.
Run: `python3 -m pytest tests/ -q` → all pass (existing `test_user_data_protected` still green: default calls remain protected).

- [ ] **Step 5: Commit**

```bash
git add core/safety.py core/deleter.py tests/test_safety.py tests/test_deleter.py tests/test_large_files.py
git commit -m "feat: two-tier protection - Soft-Protected yields to explicit user selection"
```

---

### Task 3: Scanner performance (single-walk temp scan, shallow var/folders)

**Files:**
- Modify: `scanner/system_data.py`
- Test: `tests/test_system_data.py`

**Interfaces:**
- Produces: `scan_temp_files()` does ONE `rglob("*")` walk per cache dir, matching all `TEMP_PATTERNS` suffixes per file via `fnmatch`; `/private/var/folders` is scanned at depth ≤ 2 (its `<hash>/<T|C|0>` layout) treating each subdir as one entry, like `scan_caches` treats top-level dirs. Public signatures unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_system_data.py`:

```python
def test_scan_temp_files_single_walk(monkeypatch, tmp_path):
    cache = tmp_path / "Caches"
    (cache / "deep" / "deeper").mkdir(parents=True)
    (cache / "a.tmp").write_bytes(b"1")
    (cache / "deep" / "b.bak").write_bytes(b"22")
    (cache / "deep" / "deeper" / "c.log").write_bytes(b"333")
    (cache / "deep" / "keep.dat").write_bytes(b"x")
    monkeypatch.setattr("scanner.system_data.CACHE_DIRS", [cache])

    walks = {"n": 0}
    import scanner.system_data as sd
    real_rglob = Path.rglob

    def counting_rglob(self, pattern):
        walks["n"] += 1
        return real_rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", counting_rglob)
    result = sd.scan_temp_files()
    paths = {f["path"] for f in result.files}
    assert paths == {str(cache / "a.tmp"), str(cache / "deep" / "b.bak"),
                     str(cache / "deep" / "deeper" / "c.log")}
    assert walks["n"] == 1  # one walk for one cache dir, not len(TEMP_PATTERNS)
```

(Import `Path` from pathlib at the top of the test file if not present.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_system_data.py -v -k single_walk`
Expected: FAIL (`walks["n"] == 7`).

- [ ] **Step 3: Implement**

In `scanner/system_data.py`, add `import fnmatch` and rewrite `scan_temp_files`:

```python
def scan_temp_files() -> ScanResult:
    """Scan for temporary files. One walk per cache dir; all patterns matched per file."""
    result = ScanResult("temp", "Temporary Files")
    for cache_dir in CACHE_DIRS:
        if not cache_dir.exists():
            continue
        try:
            for item in cache_dir.rglob("*"):
                if not item.is_file():
                    continue
                name = item.name
                if not any(fnmatch.fnmatch(name, pat) for pat in TEMP_PATTERNS):
                    continue
                try:
                    result.add_file(str(item), item.stat().st_size,
                                    file_age_days(item))
                except (OSError, PermissionError):
                    pass
        except (OSError, PermissionError):
            pass
    return result
```

Then bound the `/private/var/folders` cost in `scan_caches`: it already iterates only `cache_dir.iterdir()` (top level, sized via `get_dir_size`) — that is acceptable. But `scan_temp_files` walking `/private/var/folders` exhaustively is the killer: split `CACHE_DIRS` so temp-scanning skips it:

```python
# Dirs cheap enough to walk exhaustively for temp-file patterns
TEMP_SCAN_DIRS = [d for d in CACHE_DIRS if d != Path("/private/var/folders")]
```

and iterate `TEMP_SCAN_DIRS` (not `CACHE_DIRS`) in `scan_temp_files`. Update the Step-1 test's monkeypatch target from `CACHE_DIRS` to `TEMP_SCAN_DIRS`.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_system_data.py -v` → all pass. Full suite: green.

- [ ] **Step 5: Commit**

```bash
git add scanner/system_data.py tests/test_system_data.py
git commit -m "perf: single-walk temp scan; exclude var/folders from exhaustive temp walk"
```

---

### Task 4: Hygiene bundle from phase-1 final review

**Files:**
- Modify: `tests/test_system_data.py`, `tests/test_safety.py`, `tests/test_app_remnants.py`, `tests/test_privacy.py`, `tests/test_helpers.py`, `core/safety.py`

**Interfaces:**
- Produces: tier-1/2 reason strings name the matched root (e.g. `"macOS system path (/System)"`, `"personal data (~/Documents)"`); everything else is tests only.

- [ ] **Step 1: Tier reasons name the matched root (test first)**

Add to `tests/test_safety.py`:

```python
def test_reasons_name_matched_root():
    _, reason = is_protected(Path("/System/Library/x"), running={})
    assert "/System" in reason
    _, reason = is_protected(HOME / "Documents" / "f.txt", running={})
    assert "Documents" in reason
```

Run it (FAIL), then in `core/safety.py` change `_under_any` to return the matched root and use it:

```python
def _match_root(path: Path, roots: list[Path]) -> Path | None:
    for r in roots:
        if path == r or path.is_relative_to(r):
            return r
    return None
```

Rewrite the tier checks to use `_match_root` (keep `_under_any` semantics via `_match_root(...) is not None` for the exemption check), producing reasons:
- system: `f"macOS system path ({root})"`
- hard: `f"personal data ({root})"`
- soft: `f"personal data ({root} - use Space Finder to remove individually)"`

Update any existing test asserting the old literal reason text (`grep -n "personal data\|macOS system path" tests/`), keeping assertions on substrings that still hold.

- [ ] **Step 2: scan_all junk-only test patches HOME**

In `tests/test_system_data.py::test_scan_all_returns_only_junk_categories`, add `monkeypatch.setattr("scanner.system_data.HOME", tmp_path)` so a reintroduced user-data scan deterministically fails the test (it currently only fails if the real ~/Downloads is non-empty).

- [ ] **Step 3: resolve() fail-safe test**

Add to `tests/test_safety.py`:

```python
def test_unresolvable_path_fails_closed(tmp_path):
    loop = tmp_path / "loop"
    loop.symlink_to(loop, target_is_directory=True)
    protected, reason = is_protected(loop / "x", running={})
    assert protected
    assert reason
```

(A self-referential symlink makes `resolve()` raise `OSError(ELOOP)`; if on some macOS it resolves instead, `pytest.skip` inside the test after checking — but try the plain assert first.)

- [ ] **Step 4: app_remnants missing-bundle test**

Add to `tests/test_app_remnants.py`:

```python
def test_uninstall_missing_bundle_returns_empty_report(tmp_path, monkeypatch, no_running_apps):
    monkeypatch.setattr("cleaner.app_remnants.APPLICATIONS_DIR", tmp_path)
    monkeypatch.setattr("cleaner.app_remnants.find_leftovers", lambda name: [])
    result = uninstall_app("GhostApp", dry_run=False)
    assert result["app"].results == []
    assert result["app"].category == "app_bundle"
```

- [ ] **Step 5: privacy real-run test**

Add to `tests/test_privacy.py`:

```python
def test_clean_browser_data_real_run_trashes(tmp_path, monkeypatch, fake_trash):
    cache_dir = tmp_path / "BrowserCache"
    cache_dir.mkdir()
    monkeypatch.setattr("cleaner.privacy.scan_browser_data", lambda: [
        {"browser": "T", "type": "caches", "path": str(cache_dir), "size": 10},
    ])
    report = clean_browser_data(dry_run=False)
    assert not cache_dir.exists()
    assert (fake_trash / "BrowserCache").exists()
    assert len(report.trashed) == 1
```

- [ ] **Step 6: Delete the two pass-body tests**

In `tests/test_app_remnants.py` delete `test_get_installed_apps` if its body is `pass`-only (implement nothing); in `tests/test_helpers.py` delete `test_run_command_timeout` (body is a comment + `pass`). Also fix the stale comment in `tests/test_registry.py` claiming `browser_history` is passed to safe_delete by a cleaner (reword: "reserved for future cleaners").

- [ ] **Step 7: Full suite, commit**

Run: `python3 -m pytest tests/ -q` → all green.

```bash
git add core/safety.py tests/
git commit -m "chore: phase-1 review hygiene - named reasons, deterministic tests, coverage gaps"
```

---

### Task 5: `duplicates` registry category

**Files:**
- Modify: `core/registry.py`, `tests/test_registry.py`

**Interfaces:**
- Produces: registry key `duplicates` — RISKY, `user_data=True`, `via_trash=True`, explanation mentioning the kept copy. user_data set becomes `{downloads, ios_backups, large_files, duplicates}`.

- [ ] **Step 1: Failing tests**

In `tests/test_registry.py`: update `test_user_data_categories` expected set to `{"downloads", "ios_backups", "large_files", "duplicates"}`; add `"duplicates"` to the all-categories list.

- [ ] **Step 2: Run** → FAIL. **Implement:** add after `large_files` in `core/registry.py`:

```python
    Category("duplicates", Level.RISKY,
             "Extra copies of identical files. One copy of each is always kept - you choose which copies go.",
             user_data=True),
```

- [ ] **Step 3: Run tests** (`tests/test_registry.py` then full suite) → green. **Commit:**

```bash
git add core/registry.py tests/test_registry.py
git commit -m "feat: duplicates registry category (RISKY, user_data, keep-one wording)"
```

Also append the row to the spec's registry table in `docs/superpowers/specs/2026-07-16-safety-core-design.md` (`| duplicates | RISKY | ✓ | ✓ |` after large_files) and the missing `| app_bundle | CAUTION | – | ✓ |` row flagged in review; include in this commit.

---

### Task 6: CategoryHeader and ReportView widgets

**Files:**
- Create: `ui/widgets/__init__.py` (empty), `ui/widgets/category_header.py`, `ui/widgets/report_view.py`, `ui/screens/__init__.py` (empty)
- Test: `tests/test_widgets.py`

**Interfaces:**
- Produces: `CategoryHeader(category_key)` (Static showing `[LEVEL] explanation` + non-via_trash suffix); `render_report(report) -> str` pure function; `ReportView` Static with `.show(reports: list[DeleteReport])`. Later screens import these.

- [ ] **Step 1: Failing tests**

Create `tests/test_widgets.py`:

```python
from core.deleter import DeleteReport, Outcome, PathResult
from ui.widgets.category_header import header_markup
from ui.widgets.report_view import render_report


def test_header_markup_shows_level_and_explanation():
    text = header_markup("caches")
    assert "[green]" in text and "SAFE" in text
    assert "rebuild" in text  # from the registry explanation


def test_header_markup_labels_non_trash_categories():
    text = header_markup("brew_cleanup")
    assert "not recoverable via Trash" in text


def test_render_report_dry_and_real_wording():
    r = DeleteReport(category="caches", dry_run=True)
    r.results.append(PathResult("/tmp/x", Outcome.TRASHED, 123))
    r.results.append(PathResult("/tmp/y", Outcome.SKIPPED, 5, "Chrome is running"))
    out = render_report(r)
    assert "Would move to Trash" in out and "~123 B" in out
    assert "Chrome is running" in out
    assert "freed" not in out.lower()

    r2 = DeleteReport(category="caches", dry_run=False)
    r2.results.append(PathResult("/tmp/x", Outcome.FAILED, 1, "disk full"))
    out2 = render_report(r2)
    assert "Moved to Trash: 0" in out2 and "disk full" in out2
```

- [ ] **Step 2: Run** → FAIL (modules missing).

- [ ] **Step 3: Implement**

`ui/widgets/category_header.py`:

```python
"""[LEVEL] badge + plain-English explanation, straight from the registry."""
from textual.widgets import Static

from core import registry

LEVEL_STYLES = {"SAFE": "green", "CAUTION": "yellow", "RISKY": "red"}


def header_markup(category_key: str) -> str:
    cat = registry.get(category_key)
    style = LEVEL_STYLES[cat.level.value]
    suffix = (" [dim](cleared directly - not recoverable via Trash)[/dim]"
              if not cat.via_trash else "")
    return f"[{style}]\\[{cat.level.value}][/{style}] {cat.explanation}{suffix}"


class CategoryHeader(Static):
    def __init__(self, category_key: str, **kwargs) -> None:
        super().__init__(header_markup(category_key), **kwargs)
        self.category_key = category_key
```

`ui/widgets/report_view.py`:

```python
"""The sole renderer for DeleteReports. Wording is bound by CONTEXT.md."""
from textual.widgets import Static

from core.deleter import DeleteReport
from utils.helpers import format_size


def render_report(report: DeleteReport) -> str:
    verb = "Would move to Trash" if report.dry_run else "Moved to Trash"
    lines = [f"[green]{verb}:[/green] {len(report.trashed)} items "
             f"(~{format_size(report.trashed_bytes)})"]
    for r in report.skipped:
        lines.append(f"  [yellow]Skipped:[/yellow] …{r.path[-60:]} - {r.reason}")
    for r in report.failed:
        lines.append(f"  [red]Failed:[/red] …{r.path[-60:]} - {r.reason}")
    return "\n".join(lines)


class ReportView(Static):
    def show(self, reports: list[DeleteReport]) -> None:
        self.update("\n\n".join(render_report(r) for r in reports))
```

- [ ] **Step 4: Run tests + full suite** → green. **Commit:**

```bash
git add ui/widgets/ ui/screens/__init__.py tests/test_widgets.py
git commit -m "feat: CategoryHeader and ReportView widgets"
```

---

### Task 7: Gate modals

**Files:**
- Create: `ui/widgets/gates.py`
- Test: `tests/test_gates.py`

**Interfaces:**
- Produces: `ConfirmModal(prompt)` → `ModalScreen[bool]`, buttons Cancel (default focus) / Confirm, Escape dismisses False. `TypedGateModal(prompt)` → `ModalScreen[bool]`, dismisses True only when the input submits literal "yes" (case-insensitive, stripped); Escape/Cancel → False. These are the ONLY gate implementations.

- [ ] **Step 1: Failing tests**

Create `tests/test_gates.py`:

```python
from textual.app import App

from ui.widgets.gates import ConfirmModal, TypedGateModal


class Host(App):
    def __init__(self, modal):
        super().__init__()
        self._modal = modal
        self.result: bool | None = None

    def on_mount(self) -> None:
        self.push_screen(self._modal, lambda v: setattr(self, "result", v))


async def test_confirm_modal_confirm_and_cancel():
    host = Host(ConfirmModal("Move 3 items (~1.2 GB) to Trash?"))
    async with host.run_test() as pilot:
        await pilot.click("#confirm")
    assert host.result is True

    host = Host(ConfirmModal("Move 3 items to Trash?"))
    async with host.run_test() as pilot:
        await pilot.press("escape")
    assert host.result is False


async def test_typed_gate_requires_literal_yes():
    host = Host(TypedGateModal("Delete 2 snapshots"))
    async with host.run_test() as pilot:
        await pilot.click("#gate-input")
        await pilot.press(*"sure", "enter")
    assert host.result is False

    host = Host(TypedGateModal("Delete 2 snapshots"))
    async with host.run_test() as pilot:
        await pilot.click("#gate-input")
        await pilot.press(*"YES", "enter")
    assert host.result is True


async def test_typed_gate_escape_rejects():
    host = Host(TypedGateModal("Delete"))
    async with host.run_test() as pilot:
        await pilot.press("escape")
    assert host.result is False
```

- [ ] **Step 2: Run** → FAIL. **Implement** `ui/widgets/gates.py`:

```python
"""Gate modals - the only confirmation implementations in the UI.

ConfirmModal: y/N for trashing user-selected items (recoverable).
TypedGateModal: literal 'yes' for Irreversible Actions (not recoverable).
"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [("escape", "dismiss(False)", "Cancel")]
    DEFAULT_CSS = """
    ConfirmModal { align: center middle; }
    ConfirmModal #gate-box { width: 60; height: auto; border: thick $warning; padding: 1 2; }
    """

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="gate-box"):
            yield Label(self.prompt)
            with Horizontal():
                yield Button("Cancel", variant="primary", id="cancel")
                yield Button("Move to Trash", variant="warning", id="confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


class TypedGateModal(ModalScreen[bool]):
    BINDINGS = [("escape", "dismiss(False)", "Cancel")]
    DEFAULT_CSS = """
    TypedGateModal { align: center middle; }
    TypedGateModal #gate-box { width: 60; height: auto; border: thick $error; padding: 1 2; }
    """

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="gate-box"):
            yield Label(f"[bold red]{self.prompt}[/bold red]")
            yield Label("This cannot be undone. Type 'yes' to proceed:")
            yield Input(placeholder="no", id="gate-input")
            yield Button("Cancel", variant="primary", id="cancel")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip().lower() == "yes")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(False)
```

- [ ] **Step 3: Run tests + full suite** → green. **Commit:**

```bash
git add ui/widgets/gates.py tests/test_gates.py
git commit -m "feat: ConfirmModal and TypedGateModal - the UI's only gates"
```

---

### Task 8: Junk screen (System Data)

**Files:**
- Create: `ui/screens/junk.py`
- Test: `tests/test_screen_junk.py`

**Interfaces:**
- Consumes: `scan_all`, `clean_files` (cleaner/system_data), `reclaim`, widgets from Tasks 6-7.
- Produces: `JunkScreen(Screen)` — bindings: `escape` back, `d` dry run, `c` clean. Streams categories as they scan; after a real clean with trashed items, mounts TypedGateModal for reclaim.

- [ ] **Step 1: Failing test**

Create `tests/test_screen_junk.py`:

```python
from pathlib import Path

from textual.app import App

from scanner.system_data import ScanResult
from ui.screens.junk import JunkScreen


class Host(App):
    def on_mount(self):
        self.push_screen(JunkScreen())


def _fixture_scan(tmp_path):
    f = tmp_path / "old.cache"
    f.write_bytes(b"12345")
    sr = ScanResult("caches", "User Caches")
    sr.add_file(str(f), 5, 30)
    return f, sr


async def test_junk_scan_clean_and_decline_reclaim(tmp_path, monkeypatch, fake_trash):
    f, sr = _fixture_scan(tmp_path)
    monkeypatch.setattr("ui.screens.junk.scan_all", lambda: [sr])

    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()          # let the scan worker post results
        assert host.screen.results   # category arrived
        await pilot.press("c")       # real clean
        await pilot.pause()
        assert not f.exists()
        assert (fake_trash / "old.cache").exists()
        # reclaim gate mounted; escape = decline
        await pilot.press("escape")
        await pilot.pause()
        assert (fake_trash / "old.cache").exists()  # nothing permanently deleted


async def test_junk_dry_run_touches_nothing(tmp_path, monkeypatch, fake_trash):
    f, sr = _fixture_scan(tmp_path)
    monkeypatch.setattr("ui.screens.junk.scan_all", lambda: [sr])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert f.exists()
        report_text = str(host.screen.query_one("#report").renderable)
        assert "Would move to Trash" in report_text
```

- [ ] **Step 2: Run** → FAIL. **Implement** `ui/screens/junk.py`:

```python
"""System Data screen - Junk only; bulk cleaning allowed."""
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from cleaner.system_data import clean_files
from core.deleter import DeleteReport, reclaim
from scanner.system_data import scan_all
from ui.widgets.category_header import CategoryHeader
from ui.widgets.gates import TypedGateModal
from ui.widgets.report_view import ReportView
from utils.helpers import format_size


class JunkScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("d", "dry_run", "Dry Run"),
        ("c", "clean", "Clean"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="junk-body")
        yield ReportView(id="report")
        yield Footer()

    def on_mount(self) -> None:
        self.results = {}
        self.sub_title = "System Data (Junk) - scanning…"
        self.run_worker(self._scan, thread=True)

    def _scan(self) -> None:
        for res in scan_all():
            self.app.call_from_thread(self._add_category, res)
        self.app.call_from_thread(self._scan_done)

    def _add_category(self, res) -> None:
        self.results[res.category] = res
        body = self.query_one("#junk-body")
        body.mount(CategoryHeader(res.category))
        body.mount(Static(f"  {res.name}: {res.file_count} items (~{res.human_size})"))

    def _scan_done(self) -> None:
        self.sub_title = "System Data (Junk)"

    def action_dry_run(self) -> None:
        self._run_clean(dry_run=True)

    def action_clean(self) -> None:
        self._run_clean(dry_run=False)

    def _run_clean(self, dry_run: bool) -> None:
        def _work() -> list[DeleteReport]:
            return [clean_files(res, dry_run=dry_run)
                    for res in self.results.values()]

        def _done(reports: list[DeleteReport]) -> None:
            self.query_one(ReportView).show(reports)
            if not dry_run and any(r.trashed for r in reports):
                self._offer_reclaim(reports)

        self.run_worker(lambda: self.app.call_from_thread(_done, _work()),
                        thread=True)

    def _offer_reclaim(self, reports: list[DeleteReport]) -> None:
        total = sum(r.trashed_bytes for r in reports)

        def _resolved(confirmed: bool | None) -> None:
            if confirmed:
                result = reclaim(reports)
                self.notify(f"Reclaimed ~{format_size(result.freed_bytes)} "
                            f"({result.deleted} items)")
            else:
                self.notify("Kept in Trash - recover anytime with Put Back.")

        self.app.push_screen(
            TypedGateModal(f"Permanently delete these items to reclaim "
                           f"~{format_size(total)}"),
            _resolved,
        )
```

- [ ] **Step 3: Run tests + full suite** → green. **Commit:**

```bash
git add ui/screens/junk.py tests/test_screen_junk.py
git commit -m "feat: Junk screen - streaming scan, dry/clean, gated reclaim"
```

---

### Task 9: Space Finder screen (Downloads, iOS Backups, Large Files, Duplicates)

**Files:**
- Create: `ui/screens/space_finder.py`
- Test: `tests/test_screen_space_finder.py`

**Interfaces:**
- Consumes: `scan_space_finder` (downloads + ios_backups ScanResults), `find_large_files`, `find_duplicates`, `safe_delete`, ConfirmModal, widgets.
- Produces: `SpaceFinderScreen(Screen)` with a `TabbedContent` of four `SelectionList`s. NO select-all binding exists. `t` = Move to Trash (ConfirmModal first). Keep-One Invariant on the Duplicates tab. Item registry: `self.items: dict[str, dict[int, dict]]` keyed by tab/category then option index; duplicates carry `group` keys.

- [ ] **Step 1: Failing tests**

Create `tests/test_screen_space_finder.py`:

```python
from textual.app import App
from textual.widgets import SelectionList

from scanner.system_data import ScanResult
from ui.screens.space_finder import SpaceFinderScreen


class Host(App):
    def on_mount(self):
        self.push_screen(SpaceFinderScreen())


def _patch_scanners(monkeypatch, tmp_path, dup_paths=()):
    dl = ScanResult("downloads", "Downloads")
    f = tmp_path / "old.dmg"
    f.write_bytes(b"x" * 10)
    dl.add_file(str(f), 10, 400)
    monkeypatch.setattr("ui.screens.space_finder.scan_space_finder", lambda: [dl])
    monkeypatch.setattr("ui.screens.space_finder.find_large_files",
                        lambda **kw: [])
    groups = []
    if dup_paths:
        groups = [{"hash": "h1", "size": 4,
                   "files": [str(p) for p in dup_paths],
                   "wasted": 4 * (len(dup_paths) - 1)}]
    monkeypatch.setattr("ui.screens.space_finder.find_duplicates",
                        lambda **kw: groups)
    return f


async def test_nothing_preselected_and_no_select_all(tmp_path, monkeypatch, fake_trash):
    _patch_scanners(monkeypatch, tmp_path)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        for sl in host.screen.query(SelectionList):
            assert sl.selected == []
        bound_keys = {b[0] if isinstance(b, tuple) else b.key
                      for b in host.screen.BINDINGS}
        assert "a" not in bound_keys  # no select-all affordance


async def test_pick_confirm_trash(tmp_path, monkeypatch, fake_trash):
    f = _patch_scanners(monkeypatch, tmp_path)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        dl_list = host.screen.query_one("#list-downloads", SelectionList)
        dl_list.focus()
        await pilot.press("space")     # select the only row
        await pilot.press("t")         # Move to Trash -> ConfirmModal
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()
        assert not f.exists()
        assert (fake_trash / "old.dmg").exists()


async def test_decline_leaves_everything(tmp_path, monkeypatch, fake_trash):
    f = _patch_scanners(monkeypatch, tmp_path)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        host.screen.query_one("#list-downloads", SelectionList).focus()
        await pilot.press("space", "t")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert f.exists()


async def test_keep_one_invariant(tmp_path, monkeypatch, fake_trash):
    a = tmp_path / "a.jpg"; a.write_bytes(b"1234")
    b = tmp_path / "b.jpg"; b.write_bytes(b"1234")
    _patch_scanners(monkeypatch, tmp_path, dup_paths=(a, b))
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        dup_list = host.screen.query_one("#list-duplicates", SelectionList)
        dup_list.focus()
        await pilot.press("space")          # select copy 1 - fine
        await pilot.press("down", "space")  # try to select copy 2 - refused
        await pilot.pause()
        assert len(dup_list.selected) == 1  # one copy always kept
```

- [ ] **Step 2: Run** → FAIL. **Implement** `ui/screens/space_finder.py`:

```python
"""Space Finder - Reclaimable User Data: browse, pick individually, confirm.

Structural rules (see CONTEXT.md): nothing pre-selected, no select-all,
user_selected=True is honest because paths come from live checkbox state,
and the Duplicates tab enforces the Keep-One Invariant.
"""
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, SelectionList, TabbedContent, TabPane
from textual.widgets.selection_list import Selection

from core.deleter import safe_delete
from scanner.duplicates import find_duplicates
from scanner.large_files import find_large_files
from scanner.system_data import scan_space_finder
from ui.widgets.gates import ConfirmModal
from ui.widgets.report_view import ReportView
from utils.helpers import format_size

TABS = ("downloads", "ios_backups", "large_files", "duplicates")


class SpaceFinderScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("t", "trash_selected", "Move to Trash"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            for key in TABS:
                with TabPane(key.replace("_", " ").title(), id=f"tab-{key}"):
                    yield SelectionList(id=f"list-{key}")
        yield ReportView(id="report")
        yield Footer()

    def on_mount(self) -> None:
        # per-category: option index -> item dict; duplicates items carry "group"
        self.items: dict[str, dict[int, dict]] = {k: {} for k in TABS}
        self.sub_title = "Space Finder - scanning…"
        self.run_worker(self._scan, thread=True)

    # ---------- scanning ----------

    def _scan(self) -> None:
        for res in scan_space_finder():
            rows = [dict(f) for f in res.files]
            self.app.call_from_thread(self._fill, res.category, rows)
        large = [{"path": lf.path, "size": lf.size, "age_days": lf.age_days}
                 for lf in find_large_files(min_size_mb=100, max_results=200)]
        self.app.call_from_thread(self._fill, "large_files", large)
        dups = []
        for group in find_duplicates():
            for p in group["files"]:
                dups.append({"path": p, "size": group["size"],
                             "age_days": 0, "group": group["hash"]})
        self.app.call_from_thread(self._fill, "duplicates", dups)
        self.app.call_from_thread(self._scan_done)

    def _fill(self, category: str, rows: list[dict]) -> None:
        sel = self.query_one(f"#list-{category}", SelectionList)
        for i, item in enumerate(rows):
            self.items[category][i] = item
            age = f"{item.get('age_days', 0):>4.0f}d"
            label = f"{format_size(item['size']):>10}  {age}  …{item['path'][-70:]}"
            sel.add_option(Selection(label, i, initial_state=False))

    def _scan_done(self) -> None:
        self.sub_title = "Space Finder"

    # ---------- Keep-One Invariant ----------

    def on_selection_list_selected_changed(
        self, event: SelectionList.SelectedChanged
    ) -> None:
        sel = event.selection_list
        if sel.id != "list-duplicates":
            return
        items = self.items["duplicates"]
        selected = set(sel.selected)
        by_group: dict[str, list[int]] = {}
        for i in selected:
            by_group.setdefault(items[i]["group"], []).append(i)
        for group_hash, chosen in by_group.items():
            group_size = sum(1 for it in items.values()
                            if it["group"] == group_hash)
            if len(chosen) >= group_size:
                # refuse: deselect the highest-indexed pick and warn
                sel.deselect(chosen[-1])
                self.notify("One copy of each duplicate is always kept.",
                            severity="warning")

    # ---------- trashing ----------

    def action_trash_selected(self) -> None:
        picked: dict[str, list[dict]] = {}
        for key in TABS:
            sel = self.query_one(f"#list-{key}", SelectionList)
            rows = [self.items[key][i] for i in sel.selected]
            if rows:
                picked[key] = rows
        if not picked:
            self.notify("Nothing selected.")
            return
        count = sum(len(v) for v in picked.values())
        total = sum(f["size"] for v in picked.values() for f in v)

        def _resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self.notify("Cancelled - nothing was touched.")
                return
            reports = [
                safe_delete(rows, category, dry_run=False, user_selected=True)
                for category, rows in picked.items()
            ]
            self.query_one(ReportView).show(reports)
            self._refresh_lists(picked)

        self.app.push_screen(
            ConfirmModal(f"Move {count} item(s) (~{format_size(total)}) to Trash?"),
            _resolved,
        )

    def _refresh_lists(self, picked: dict[str, list[dict]]) -> None:
        trashed_paths = {f["path"] for v in picked.values() for f in v}
        for key in picked:
            sel = self.query_one(f"#list-{key}", SelectionList)
            keep = {i: it for i, it in self.items[key].items()
                    if it["path"] not in trashed_paths}
            sel.clear_options()
            self.items[key] = {}
            self._fill(key, list(keep.values()))
```

- [ ] **Step 3: Run tests + full suite** → green. **Commit:**

```bash
git add ui/screens/space_finder.py tests/test_screen_space_finder.py
git commit -m "feat: Space Finder screen - four pick tabs, Keep-One Invariant, no select-all"
```

---

### Task 10: Privacy and Optimize screens

**Files:**
- Create: `ui/screens/privacy.py`, `ui/screens/optimize.py`
- Test: `tests/test_screen_privacy.py`, `tests/test_screen_optimize.py`

**Interfaces:**
- Consumes: `clean_privacy`, `clear_recently_used`, `optimize_mac`, widgets/gates.
- Produces: `PrivacyScreen` (bindings: escape, `d` dry run, `c` clean, `r` clear recents → TypedGateModal); `OptimizeScreen` (escape, `d`, `c`; DeleteReport outputs through ReportView, external-tool dict outputs as labeled lines).

- [ ] **Step 1: Failing tests**

`tests/test_screen_privacy.py`:

```python
from textual.app import App

from core.deleter import DeleteReport
from ui.screens.privacy import PrivacyScreen


class Host(App):
    def on_mount(self):
        self.push_screen(PrivacyScreen())


async def test_privacy_clean_shows_reports(monkeypatch, fake_trash):
    empty = {"browser_cache": DeleteReport("browser_cache", dry_run=True),
             "tracking_data": DeleteReport("tracking_data", dry_run=True)}
    monkeypatch.setattr("ui.screens.privacy.clean_privacy",
                        lambda dry_run: empty)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        text = str(host.screen.query_one("#report").renderable)
        assert "Would move to Trash" in text


async def test_recents_gate_blocks_without_yes(monkeypatch):
    calls = []
    monkeypatch.setattr("ui.screens.privacy.clear_recently_used",
                        lambda dry_run=False: calls.append(dry_run) or
                        {"cleared": 1, "failed": 0})
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        await pilot.press("escape")   # decline the typed gate
        await pilot.pause()
    assert calls == []  # never invoked without the gate
```

`tests/test_screen_optimize.py`:

```python
from textual.app import App

from core.deleter import DeleteReport
from ui.screens.optimize import OptimizeScreen


class Host(App):
    def on_mount(self):
        self.push_screen(OptimizeScreen())


async def test_optimize_renders_reports_and_external_labels(monkeypatch, fake_trash):
    result = {
        "pip_cache": DeleteReport("pip_cache", dry_run=True),
        "brew_cleanup": {"message": "Cleaned up", "skipped": False},
        "xcode_derived_data": {"message": "No xcode_derived_data found",
                               "skipped": True},
    }
    monkeypatch.setattr("ui.screens.optimize.optimize_mac",
                        lambda dry_run: result)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        text = str(host.screen.query_one("#optimize-log").renderable)
        assert "Would move to Trash" in text          # DeleteReport rendering
        assert "not recoverable via Trash" in text    # external-tool label
        assert "SKIP" in text
```

- [ ] **Step 2: Run** → FAIL. **Implement**

`ui/screens/privacy.py`:

```python
"""Privacy screen - browser/tracking cleaning + gated recents clear."""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header

from cleaner.privacy import clean_privacy, clear_recently_used
from ui.widgets.category_header import CategoryHeader
from ui.widgets.gates import TypedGateModal
from ui.widgets.report_view import ReportView


class PrivacyScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("d", "dry_run", "Dry Run"),
        ("c", "clean", "Clean"),
        ("r", "clear_recents", "Clear Recents"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield CategoryHeader("browser_cache")
            yield CategoryHeader("tracking_data")
            yield CategoryHeader("recents")
            yield ReportView(id="report")
        yield Footer()

    def action_dry_run(self) -> None:
        self._clean(dry_run=True)

    def action_clean(self) -> None:
        self._clean(dry_run=False)

    def _clean(self, dry_run: bool) -> None:
        def _work():
            return list(clean_privacy(dry_run=dry_run).values())

        def _done(reports):
            self.query_one(ReportView).show(reports)

        self.run_worker(lambda: self.app.call_from_thread(_done, _work()),
                        thread=True)

    def action_clear_recents(self) -> None:
        def _resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self.notify("Recents kept.")
                return
            stats = clear_recently_used(dry_run=False)
            self.notify(f"Cleared {stats['cleared']} recent-items list(s)")

        self.app.push_screen(
            TypedGateModal("Clearing the recently-used list"), _resolved)
```

`ui/screens/optimize.py`:

```python
"""Optimize screen - dev caches (via Trash) + brew/npm (external tools)."""
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from cleaner.optimization import optimize_mac
from core.deleter import DeleteReport
from ui.widgets.category_header import header_markup
from ui.widgets.report_view import render_report


class OptimizeScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("d", "dry_run", "Dry Run"),
        ("c", "clean", "Optimize"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(Static(id="optimize-log"))
        yield Footer()

    def action_dry_run(self) -> None:
        self._run(dry_run=True)

    def action_clean(self) -> None:
        self._run(dry_run=False)

    def _run(self, dry_run: bool) -> None:
        def _work():
            return optimize_mac(dry_run=dry_run)

        def _done(result: dict) -> None:
            lines = []
            for task, output in result.items():
                if task == "launch_agents":
                    continue
                if isinstance(output, DeleteReport):
                    lines.append(header_markup(output.category))
                    lines.append(render_report(output))
                elif output.get("skipped"):
                    lines.append(f"[dim]SKIP[/dim] {task}")
                else:
                    lines.append(header_markup(task))
                    lines.append(f"  [green]OK[/green] {output.get('message', 'Done')}")
            self.query_one("#optimize-log", Static).update("\n".join(lines))

        self.run_worker(lambda: self.app.call_from_thread(_done, _work()),
                        thread=True)
```

Note: `header_markup(task)` for external tools requires task keys to be registry keys — `brew_cleanup` and `npm_cache` are. `optimize_mac`'s dict keys must match registry keys; verify with `grep -n "def optimize_mac" -A 12 cleaner/optimization.py` and adapt key names in `_done` if any differ (report the substitution).

- [ ] **Step 3: Run tests + full suite** → green. **Commit:**

```bash
git add ui/screens/privacy.py ui/screens/optimize.py tests/test_screen_privacy.py tests/test_screen_optimize.py
git commit -m "feat: Privacy and Optimize screens"
```

---

### Task 11: Snapshots and Uninstall screens

**Files:**
- Create: `ui/screens/snapshots.py`, `ui/screens/uninstall.py`
- Test: `tests/test_screen_snapshots.py`, `tests/test_screen_uninstall.py`

**Interfaces:**
- Consumes: `list_snapshots`, `clean_snapshots` (cleaner/snapshots), `get_installed_apps` (scanner/app_remnants), `uninstall_app` (cleaner/app_remnants), gates/widgets.
- Produces: `SnapshotsScreen` (escape; `x` delete-all → TypedGateModal; real result shows `Reclaimed ~X` or the zero-delta "unknown" wording). `UninstallScreen` (escape; DataTable of apps; `enter` selects → ConfirmModal → two reports).

- [ ] **Step 1: Failing tests**

`tests/test_screen_snapshots.py`:

```python
from textual.app import App

from ui.screens.snapshots import SnapshotsScreen


class Host(App):
    def on_mount(self):
        self.push_screen(SnapshotsScreen())


async def test_snapshot_delete_gated_and_reports_reclaimed(monkeypatch):
    monkeypatch.setattr("ui.screens.snapshots.list_snapshots",
                        lambda: [{"name": "com.apple.TimeMachine.x.local"}])
    calls = []
    monkeypatch.setattr(
        "ui.screens.snapshots.clean_snapshots",
        lambda dry_run=False: calls.append(1) or
        {"deleted": 1, "failed": 0, "successes": ["x"], "failures": [],
         "reclaimed_bytes": 500})
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("escape")          # decline gate
        await pilot.pause()
        assert calls == []
        await pilot.press("x")
        await pilot.pause()
        await pilot.click("#gate-input")
        await pilot.press(*"yes", "enter")   # pass gate
        await pilot.pause()
        assert calls == [1]
        text = str(host.screen.query_one("#snap-log").renderable)
        assert "Reclaimed" in text and "500" in text


async def test_snapshot_zero_delta_shows_unknown(monkeypatch):
    monkeypatch.setattr("ui.screens.snapshots.list_snapshots",
                        lambda: [{"name": "s"}])
    monkeypatch.setattr(
        "ui.screens.snapshots.clean_snapshots",
        lambda dry_run=False: {"deleted": 1, "failed": 0, "successes": ["x"],
                               "failures": [], "reclaimed_bytes": 0})
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        await pilot.click("#gate-input")
        await pilot.press(*"yes", "enter")
        await pilot.pause()
        text = str(host.screen.query_one("#snap-log").renderable)
        assert "unknown" in text.lower()
```

`tests/test_screen_uninstall.py`:

```python
from textual.app import App

from core.deleter import DeleteReport
from ui.screens.uninstall import UninstallScreen


class Host(App):
    def on_mount(self):
        self.push_screen(UninstallScreen())


async def test_uninstall_flow_confirm(monkeypatch, fake_trash):
    monkeypatch.setattr("ui.screens.uninstall.get_installed_apps",
                        lambda: [{"name": "TestApp", "path": "/Applications/TestApp.app",
                                  "size": 1000}])
    calls = []

    def fake_uninstall(name, dry_run=False):
        calls.append((name, dry_run))
        return {"app": DeleteReport("app_bundle", dry_run=dry_run),
                "leftovers": DeleteReport("app_leftovers", dry_run=dry_run)}

    monkeypatch.setattr("ui.screens.uninstall.uninstall_app", fake_uninstall)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")     # select the row -> ConfirmModal
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()
    assert calls == [("TestApp", False)]


async def test_uninstall_decline_does_nothing(monkeypatch):
    monkeypatch.setattr("ui.screens.uninstall.get_installed_apps",
                        lambda: [{"name": "TestApp", "path": "/x", "size": 1}])
    calls = []
    monkeypatch.setattr("ui.screens.uninstall.uninstall_app",
                        lambda *a, **k: calls.append(1))
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert calls == []
```

- [ ] **Step 2: Run** → FAIL. **Implement**

`ui/screens/snapshots.py`:

```python
"""Snapshots screen - Irreversible Action; reports actually-Reclaimed space."""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from cleaner.snapshots import clean_snapshots
from scanner.snapshots import list_snapshots
from ui.widgets.category_header import CategoryHeader
from ui.widgets.gates import TypedGateModal
from utils.helpers import format_size


class SnapshotsScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("x", "delete_all", "Delete All Snapshots"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield CategoryHeader("snapshots")
            yield Static(id="snap-list")
            yield Static(id="snap-log")
        yield Footer()

    def on_mount(self) -> None:
        self.snapshots = []
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        snaps = list_snapshots()
        self.app.call_from_thread(self._show, snaps)

    def _show(self, snaps) -> None:
        self.snapshots = snaps
        listing = "\n".join(s.get("name", "?") for s in snaps) or "No snapshots found."
        self.query_one("#snap-list", Static).update(listing)

    def action_delete_all(self) -> None:
        if not self.snapshots:
            self.notify("No snapshots to delete.")
            return

        def _resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self.notify("Snapshots kept.")
                return
            self.run_worker(self._delete, thread=True)

        self.app.push_screen(
            TypedGateModal(f"Deleting {len(self.snapshots)} snapshot(s)"),
            _resolved,
        )

    def _delete(self) -> None:
        result = clean_snapshots(dry_run=False)
        self.app.call_from_thread(self._report, result)

    def _report(self, result: dict) -> None:
        reclaimed = result.get("reclaimed_bytes", 0)
        space = (f"Reclaimed ~{format_size(reclaimed)}" if reclaimed
                 else "Reclaimed: unknown (couldn't isolate the freed space)")
        self.query_one("#snap-log", Static).update(
            f"Deleted: {result.get('deleted', 0)} - {space}")
        self.run_worker(self._load, thread=True)
```

`ui/screens/uninstall.py`:

```python
"""Uninstall screen - app picker; bundle + leftovers reports."""
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header

from cleaner.app_remnants import uninstall_app
from scanner.app_remnants import get_installed_apps
from ui.widgets.gates import ConfirmModal
from ui.widgets.report_view import ReportView
from utils.helpers import format_size


class UninstallScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="apps", cursor_type="row")
        yield ReportView(id="report")
        yield Footer()

    def on_mount(self) -> None:
        self.apps = []
        table = self.query_one(DataTable)
        table.add_columns("App", "Size")
        self.run_worker(self._load, thread=True)

    def _load(self) -> None:
        apps = get_installed_apps()
        self.app.call_from_thread(self._fill, apps)

    def _fill(self, apps) -> None:
        self.apps = apps
        table = self.query_one(DataTable)
        for app_info in apps:
            table.add_row(app_info["name"], format_size(app_info["size"]))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        app_info = self.apps[event.cursor_row]
        name = app_info["name"]

        def _resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self.notify("Cancelled - nothing was touched.")
                return
            try:
                result = uninstall_app(name, dry_run=False)
            except ValueError as e:
                self.notify(str(e), severity="error")
                return
            self.query_one(ReportView).show([result["app"], result["leftovers"]])

        self.app.push_screen(
            ConfirmModal(f"Uninstall {name} (~{format_size(app_info['size'])}) "
                         f"and Trash its leftovers?"),
            _resolved,
        )
```

- [ ] **Step 3: Run tests + full suite** → green. **Commit:**

```bash
git add ui/screens/snapshots.py ui/screens/uninstall.py tests/test_screen_snapshots.py tests/test_screen_uninstall.py
git commit -m "feat: Snapshots (gated, Reclaimed wording) and Uninstall screens"
```

---

### Task 12: Dashboard and app wiring

**Files:**
- Create: `ui/screens/dashboard.py`
- Modify: `ui/app.py`
- Test: `tests/test_screen_dashboard.py` (+ extend `tests/test_app_shell.py`)

**Interfaces:**
- Produces: `DashboardScreen` — disk usage line + a `DataTable` of feature areas (name, level span, hotkey); number keys `1`-`6` push the matching screen. `CleanerApp` gains `SCREENS` routing and mounts the dashboard on start.

- [ ] **Step 1: Failing tests**

Create `tests/test_screen_dashboard.py`:

```python
from ui.app import CleanerApp
from ui.screens.junk import JunkScreen
from ui.screens.space_finder import SpaceFinderScreen


async def test_dashboard_shows_disk_and_navigates(monkeypatch, tmp_path):
    monkeypatch.setattr("ui.screens.dashboard.get_disk_usage",
                        lambda: {"total": 1000, "used": 400, "free": 600,
                                 "percent": 40.0})
    # keep pushed screens from scanning the real machine
    from scanner.system_data import ScanResult
    monkeypatch.setattr("ui.screens.junk.scan_all", lambda: [])
    app = CleanerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "600" in str(app.screen.query_one("#disk").renderable) or \
               "free" in str(app.screen.query_one("#disk").renderable)
        await pilot.press("1")
        await pilot.pause()
        assert isinstance(app.screen, JunkScreen)
        await pilot.press("escape")
        await pilot.pause()
        monkeypatch.setattr("ui.screens.space_finder.scan_space_finder", lambda: [])
        monkeypatch.setattr("ui.screens.space_finder.find_large_files", lambda **kw: [])
        monkeypatch.setattr("ui.screens.space_finder.find_duplicates", lambda **kw: [])
        await pilot.press("2")
        await pilot.pause()
        assert isinstance(app.screen, SpaceFinderScreen)
```

(Check `utils/helpers.py::get_disk_usage`'s actual return shape with `grep -n "def get_disk_usage" -A 10 utils/helpers.py` and adjust the fake + rendering accordingly; report the shape you found.)

- [ ] **Step 2: Run** → FAIL. **Implement**

`ui/screens/dashboard.py`:

```python
"""Dashboard - disk usage + feature areas. Number keys navigate."""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from utils.helpers import format_size, get_disk_usage

AREAS = [
    ("1", "System Data (Junk)", "junk", "SAFE"),
    ("2", "Space Finder", "space_finder", "RISKY"),
    ("3", "Privacy", "privacy", "SAFE/RISKY"),
    ("4", "Optimize", "optimize", "SAFE"),
    ("5", "Snapshots", "snapshots", "RISKY"),
    ("6", "Uninstall Apps", "uninstall", "CAUTION"),
]


class DashboardScreen(Screen):
    BINDINGS = [(key, f"goto('{screen}')", label)
                for key, label, screen, _ in AREAS]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Static(id="disk")
            table = DataTable(id="areas", cursor_type="row")
            yield table
        yield Footer()

    def on_mount(self) -> None:
        usage = get_disk_usage()
        self.query_one("#disk", Static).update(
            f"Disk: {format_size(usage['free'])} free of "
            f"{format_size(usage['total'])} ({usage['percent']:.0f}% used)")
        table = self.query_one(DataTable)
        table.add_columns("Key", "Area", "Levels")
        for key, label, _, levels in AREAS:
            table.add_row(key, label, levels)

    def action_goto(self, screen: str) -> None:
        self.app.push_screen(screen)
```

`ui/app.py` becomes:

```python
"""CleanerApp - the Textual application."""
from textual.app import App

from ui.screens.dashboard import DashboardScreen
from ui.screens.junk import JunkScreen
from ui.screens.optimize import OptimizeScreen
from ui.screens.privacy import PrivacyScreen
from ui.screens.snapshots import SnapshotsScreen
from ui.screens.space_finder import SpaceFinderScreen
from ui.screens.uninstall import UninstallScreen


class CleanerApp(App):
    TITLE = "Mac Cleaner"
    BINDINGS = [("q", "quit", "Quit")]
    SCREENS = {
        "junk": JunkScreen,
        "space_finder": SpaceFinderScreen,
        "privacy": PrivacyScreen,
        "optimize": OptimizeScreen,
        "snapshots": SnapshotsScreen,
        "uninstall": UninstallScreen,
    }

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen())
```

Update `tests/test_app_shell.py`'s boot test if it asserted `compose` output that changed (title + `q` binding still hold).

Note: pushing `SnapshotsScreen`/`UninstallScreen` from the dashboard test is avoided (they'd hit real `tmutil`/`/Applications` listing — the test only navigates to screens whose scanners it patched).

- [ ] **Step 3: Run tests + full suite** → green. **Commit:**

```bash
git add ui/app.py ui/screens/dashboard.py tests/test_screen_dashboard.py tests/test_app_shell.py
git commit -m "feat: dashboard + screen routing"
```

---

### Task 13: Replace main.py with the Textual entry point

**Files:**
- Modify: `main.py` (near-total deletion), `setup.py` (verify only)
- Test: `tests/test_main_entry.py`

**Interfaces:**
- Produces: `main.py` exposing `main()` that runs `CleanerApp`; all menu-loop code, Rich console helpers, and their imports deleted. The Rich dependency stays (Textual uses it; scanners don't).

- [ ] **Step 1: Failing test**

Create `tests/test_main_entry.py`:

```python
import ast
from pathlib import Path


def test_main_is_a_thin_entry_point():
    src = Path("main.py").read_text()
    tree = ast.parse(src)
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert names == {"main"}, f"menu-loop functions still present: {names - {'main'}}"
    assert "CleanerApp" in src
    assert "Prompt.ask" not in src and "console.print" not in src


def test_main_imports():
    import main  # must import cleanly without side effects
    assert callable(main.main)
```

- [ ] **Step 2: Run** → FAIL (dozens of functions). **Implement** — `main.py` becomes:

```python
#!/usr/bin/env python3
"""Mac Cleaner - entry point. The UI lives in ui/ (Textual)."""


def main() -> None:
    from ui.app import CleanerApp

    CleanerApp().run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Sweep**

Run: `grep -rn "import main\|from main import" --include="*.py" . | grep -v dist/ | grep -v test_main` — nothing else may import main's deleted helpers. Run the packaging test (still green). Run: `python3 -c "import main"`.

- [ ] **Step 4: Full suite** → green. **Commit:**

```bash
git add main.py tests/test_main_entry.py
git commit -m "feat!: main.py is now the Textual entry point; menu loop deleted"
```

---

### Task 14: Final verification + docs

**Files:**
- Modify: `README.md`
- No other code changes expected.

- [ ] **Step 1: Full suite + invariants**

Run: `python3 -m pytest tests/ -q` → all green (expect ~135+ tests).
Run the phase-1 invariant greps:

```bash
grep -rn "send2trash\|is_safe_to_delete" --include="*.py" cleaner/ scanner/ utils/ core/ ui/ main.py   # expect: only the core/trash.py docstring mention
grep -rn "shutil.rmtree\|\.unlink()\|os.remove" --include="*.py" cleaner/ scanner/ utils/ ui/ main.py  # expect: nothing (core/trash.py only)
grep -rn "safe_delete\|reclaim(" --include="*.py" ui/ | grep -v "user_selected=True" | grep "safe_delete" # every ui/ safe_delete call on user data must carry user_selected=True; junk screen calls go through cleaner functions
grep -rni "freed" ui/ main.py  # expect: only ReclaimReport.freed_bytes identifiers and "Reclaimed" wording
```

If any grep surprises, STOP and report BLOCKED with the hits.

- [ ] **Step 2: Manual smoke (the one human-eyes step)**

Run `python3 main.py` in a real terminal: dashboard renders; `1` opens Junk and streams categories; `escape` returns; `2` opens Space Finder (tabs render; nothing pre-selected); `q` quits. No tracebacks. (If running headless, note it and rely on the pilot tests.)

- [ ] **Step 3: README**

Update `README.md`'s usage section to mention the full-screen UI and keys (`1-6` navigate, `d` dry run, `c` clean, `t` move picked items to Trash, `q` quit), keeping the safety-promise paragraph from phase 1.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README covers the Textual UI"
```
