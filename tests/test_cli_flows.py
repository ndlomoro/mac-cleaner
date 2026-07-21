"""Flow tests. A FakeUI feeds scripted answers and captures output; scanners
and cleaners are monkeypatched, so no real dir or tool is ever touched. The
focus is the safety-critical control flow: gates, Keep-One refusal, and that
declining reclaim keeps items in the Trash."""
import pytest

from cli import app, flows
from core.deleter import DeleteReport, Outcome, PathResult
from scanner.system_data import ScanResult


class FakeUI:
    def __init__(self, choices=None, answers=None, confirms=None, gates=None):
        self.out: list[str] = []
        self._choices = list(choices or [])
        self._answers = list(answers or [])
        self._confirms = list(confirms or [])
        self._gates = list(gates or [])

    def print(self, r=""):
        self.out.append(str(r))

    def lines(self, lines):
        self.out.extend(lines)

    def rule(self, title=""):
        self.out.append(title)

    def notify(self, m):
        self.out.append(m)

    def choose(self, prompt, choices):
        return self._choices.pop(0)

    def ask(self, prompt, default=""):
        return self._answers.pop(0)

    def confirm(self, message):
        return self._confirms.pop(0)

    def typed_gate(self, message):
        return self._gates.pop(0)

    def pause(self):
        pass

    @property
    def text(self):
        return "\n".join(self.out)


def _report(category, dry_run, trashed=()):
    r = DeleteReport(category=category, dry_run=dry_run)
    for path, size in trashed:
        r.results.append(PathResult(path, Outcome.TRASHED, size,
                                    trash_path="" if dry_run else f"/T/{path}"))
    return r


def _scan(category, name, files):
    """A ScanResult; files is a list of (path, size)."""
    r = ScanResult(category, name)
    for path, size in files:
        r.add_file(path, size, 0)
    return r


# ---- 2. System Junk (per-category selection) ----

def _junk_scan(monkeypatch):
    """Three categories the user can pick between; records what clean_files ran."""
    results = [
        _scan("caches", "User Caches", [("/c/a", 100), ("/c/b", 200)]),
        _scan("logs", "System & App Logs", [("/l/a", 50)]),
        _scan("temp", "Temporary Files", [("/t/a", 10), ("/t/b", 20), ("/t/c", 30)]),
    ]
    monkeypatch.setattr(flows, "scan_all", lambda: results)
    cleaned = []

    def fake_clean(scan_result, dry_run=False):
        cleaned.append(scan_result.category)
        return _report(scan_result.category, dry_run,
                       [(f["path"], f["size"]) for f in scan_result.files])

    monkeypatch.setattr(flows, "clean_files", fake_clean)
    return cleaned


def test_system_junk_picks_single_category(monkeypatch):
    cleaned = _junk_scan(monkeypatch)
    reclaimed = []
    monkeypatch.setattr(flows, "reclaim", lambda reports: reclaimed.append(reports))
    # pick only Temporary Files (row 3); confirm trash; decline reclaim
    ui = FakeUI(answers=["3"], confirms=[True], gates=[False])
    flows.system_junk(ui)
    assert cleaned == ["temp"]  # caches/logs untouched
    assert any("Moved to Trash" in line for line in ui.out)
    assert any("Kept in Trash" in line for line in ui.out)
    assert reclaimed == []


def test_system_junk_all_categories(monkeypatch):
    cleaned = _junk_scan(monkeypatch)
    monkeypatch.setattr(flows, "reclaim", lambda reports: None)
    ui = FakeUI(answers=["a"], confirms=[True], gates=[False])
    flows.system_junk(ui)
    assert cleaned == ["caches", "logs", "temp"]


def test_system_junk_back_selects_nothing(monkeypatch):
    cleaned = _junk_scan(monkeypatch)
    ui = FakeUI(answers=["b"])
    flows.system_junk(ui)
    assert cleaned == []


def test_system_junk_cancel_does_not_delete(monkeypatch):
    cleaned = _junk_scan(monkeypatch)
    ui = FakeUI(answers=["1,3"], confirms=[False])
    flows.system_junk(ui)
    assert cleaned == []
    assert any("Cancelled" in line for line in ui.out)


def test_system_junk_nothing_found(monkeypatch):
    monkeypatch.setattr(flows, "scan_all", lambda: [])
    ui = FakeUI()
    flows.system_junk(ui)
    assert any("No cleanable junk" in line for line in ui.out)


# ---- 3. Space Finder / Keep-One ----

def _dup_scan(monkeypatch):
    """One duplicate group of two identical copies; /a is the keeper."""
    monkeypatch.setattr(flows, "scan_space_finder", lambda: [])
    monkeypatch.setattr(flows, "find_large_files",
                        lambda **kw: [])
    monkeypatch.setattr(flows, "find_duplicates",
                        lambda: [{"hash": "h1", "size": 100,
                                  "files": ["/a", "/b"]}])
    monkeypatch.setattr(flows, "pick_keeper", lambda files: files[0])


def test_space_finder_refuses_emptying_a_group(monkeypatch):
    _dup_scan(monkeypatch)
    called = []
    monkeypatch.setattr(flows, "trash_selection",
                        lambda *a, **k: called.append(a) or [])

    # view duplicates tab, select BOTH copies, try to trash, then back
    ui = FakeUI(choices=["4", "t", "b"], answers=["1 2"])
    flows.space_finder(ui)

    assert any(flows.KEEP_ONE_MSG in line for line in ui.out)
    assert called == []  # never reached the deletion interface


def test_space_finder_trash_non_keeper_then_decline_reclaim(monkeypatch):
    _dup_scan(monkeypatch)
    seen = {}

    def fake_trash(submission, groups, dry_run=False):
        seen["submission"] = submission
        return [_report("duplicates", False, [("/b", 100)])]

    monkeypatch.setattr(flows, "trash_selection", fake_trash)
    reclaimed = []
    monkeypatch.setattr(flows, "reclaim", lambda reports: reclaimed.append(reports))

    # k = select non-keepers, t = trash, b = back; confirm trash, decline reclaim
    ui = FakeUI(choices=["k", "t", "b"], confirms=[True], gates=[False])
    flows.space_finder(ui)

    # only the non-keeper /b was submitted, from the duplicates tab
    assert [r["path"] for r in seen["submission"]["duplicates"]] == ["/b"]
    assert any("Kept in Trash" in line for line in ui.out)
    assert reclaimed == []


def test_space_finder_empty_scan_returns(monkeypatch):
    monkeypatch.setattr(flows, "scan_space_finder", lambda: [])
    monkeypatch.setattr(flows, "find_large_files", lambda **kw: [])
    monkeypatch.setattr(flows, "find_duplicates", lambda: [])
    monkeypatch.setattr(flows, "pick_keeper", lambda files: files[0])
    ui = FakeUI()
    flows.space_finder(ui)
    assert any("Nothing to reclaim" in line for line in ui.out)


# ---- 4. Privacy: recents is an Irreversible Action (typed gate) ----

def _privacy_scan(monkeypatch):
    monkeypatch.setattr(flows, "scan_browser_data", lambda: [])
    monkeypatch.setattr(flows, "scan_tracking_data", lambda: [])
    monkeypatch.setattr(flows, "scan_recently_used",
                        lambda: [{"type": "recent_items", "path": "/r", "size": 1}])


def test_privacy_recents_typed_gate_confirmed(monkeypatch):
    _privacy_scan(monkeypatch)
    cleared = []
    monkeypatch.setattr(flows, "clear_recently_used",
                        lambda dry_run=False: cleared.append(dry_run) or
                        {"cleared": 1, "failed": 0})
    ui = FakeUI(choices=["2"], gates=[True])
    flows.privacy(ui)
    assert cleared == [False]
    assert any("Cleared 1" in line for line in ui.out)


def test_privacy_recents_typed_gate_declined(monkeypatch):
    _privacy_scan(monkeypatch)
    cleared = []
    monkeypatch.setattr(flows, "clear_recently_used",
                        lambda dry_run=False: cleared.append(dry_run))
    ui = FakeUI(choices=["2"], gates=[False])
    flows.privacy(ui)
    assert cleared == []  # declined gate never clears
    assert any("Left unchanged" in line for line in ui.out)


# ---- 6. Snapshots: Irreversible, typed gate, no reclaim ----

def test_snapshots_typed_gate_confirmed(monkeypatch):
    monkeypatch.setattr(flows, "list_snapshots", lambda: [{"name": "snap.1"}])
    deleted = []
    monkeypatch.setattr(flows, "clean_snapshots",
                        lambda dry_run=False: deleted.append(dry_run) or
                        {"deleted": 1, "failed": 0})
    ui = FakeUI(gates=[True])
    flows.snapshots(ui)
    assert deleted == [False]
    assert any("Deleted 1" in line for line in ui.out)


def test_snapshots_typed_gate_declined(monkeypatch):
    monkeypatch.setattr(flows, "list_snapshots", lambda: [{"name": "snap.1"}])
    deleted = []
    monkeypatch.setattr(flows, "clean_snapshots",
                        lambda dry_run=False: deleted.append(dry_run))
    ui = FakeUI(gates=[False])
    flows.snapshots(ui)
    assert deleted == []
    assert any("Left unchanged" in line for line in ui.out)


def test_snapshots_none_found(monkeypatch):
    monkeypatch.setattr(flows, "list_snapshots", lambda: [])
    ui = FakeUI()
    flows.snapshots(ui)
    assert any("No local snapshots" in line for line in ui.out)


# ---- menu loop ----

def test_menu_quit(monkeypatch):
    monkeypatch.setattr(app, "disk_panel", lambda: "DISK")
    ui = FakeUI(choices=["q"])
    app.run(ui)
    assert any("Bye" in line for line in ui.out)


def test_menu_dispatches_then_returns(monkeypatch):
    monkeypatch.setattr(app, "disk_panel", lambda: "DISK")
    hit = []
    monkeypatch.setattr(flows, "quick_scan", lambda ui: hit.append("scan"))
    ui = FakeUI(choices=["1", "q"])
    app.run(ui)
    assert hit == ["scan"]
