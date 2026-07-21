"""Flow tests. A FakeUI feeds scripted answers and captures output; scanners
and cleaners are monkeypatched, so no real dir or tool is ever touched. The
focus is the safety-critical control flow: gates, Keep-One refusal, and that
declining reclaim keeps items in the Trash."""
import pytest

from cli import app, flows
from core.deleter import DeleteReport, Outcome, PathResult


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


# ---- 2. System Junk ----

def test_system_junk_trashes_then_offers_reclaim(monkeypatch):
    calls = []

    def fake_clean(dry_run=False):
        calls.append(dry_run)
        return {"caches": _report("caches", dry_run, [("/c/a", 100)])}

    monkeypatch.setattr(flows, "clean_system_data", fake_clean)
    reclaimed = []
    monkeypatch.setattr(flows, "reclaim", lambda reports: reclaimed.append(reports))

    ui = FakeUI(confirms=[True], gates=[False])  # confirm trash, decline reclaim
    flows.system_junk(ui)

    assert calls == [True, False]  # dry preview, then real
    assert any("Moved to Trash" in line for line in ui.out)
    assert any("Kept in Trash" in line for line in ui.out)
    assert reclaimed == []  # declined -> reclaim never called


def test_system_junk_cancel_does_not_delete(monkeypatch):
    calls = []

    def fake_clean(dry_run=False):
        calls.append(dry_run)
        return {"caches": _report("caches", dry_run, [("/c/a", 100)])}

    monkeypatch.setattr(flows, "clean_system_data", fake_clean)
    ui = FakeUI(confirms=[False])
    flows.system_junk(ui)

    assert calls == [True]  # only the dry preview ran
    assert any("Cancelled" in line for line in ui.out)


def test_system_junk_nothing_found(monkeypatch):
    monkeypatch.setattr(flows, "clean_system_data",
                        lambda dry_run=False: {})
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
