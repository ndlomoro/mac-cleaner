import pytest
import scanner.snapshots
import cleaner.snapshots
from scanner.snapshots import list_snapshots
from cleaner.snapshots import clean_snapshots, delete_snapshot, delete_all_snapshots

def test_list_snapshots(monkeypatch):
    # Mock run_command to return tmutil output
    mock_stdout = "com.apple.TimeMachine.update-2026-06-11-120000.local\ncom.apple.TimeMachine.update-2026-06-11-130000.local\n"
    monkeypatch.setattr(scanner.snapshots, "run_command", lambda cmd: (mock_stdout, "", 0))
    
    snaps = list_snapshots()
    assert len(snaps) == 2
    assert snaps[0]["name"] == "com.apple.TimeMachine.update-2026-06-11-120000.local"
    assert snaps[0]["date"] == "2026-06-11-120000.local"

def test_list_snapshots_empty_or_fail(monkeypatch):
    monkeypatch.setattr(scanner.snapshots, "run_command", lambda cmd: ("", "error", 1))
    assert list_snapshots() == []

def test_delete_snapshot(monkeypatch):
    monkeypatch.setattr(cleaner.snapshots, "run_command", lambda cmd, sudo=False: ("", "", 0))
    success, msg = delete_snapshot("com.apple.TimeMachine.2026-06-11-120000.local")
    assert success is True
    assert "Deleted snapshot" in msg

    monkeypatch.setattr(cleaner.snapshots, "run_command", lambda cmd, sudo=False: ("", "permission denied", 1))
    success, msg = delete_snapshot("com.apple.TimeMachine.2026-06-11-120000.local")
    assert success is False
    assert "Failed" in msg

def test_clean_snapshots_dry_run(monkeypatch):
    # Mock list_snapshots
    mock_snaps = [
        {"name": "com.apple.TimeMachine.1", "date": "1"},
        {"name": "com.apple.TimeMachine.2", "date": "2"}
    ]
    monkeypatch.setattr(cleaner.snapshots, "list_snapshots", lambda: mock_snaps)
    
    res = clean_snapshots(dry_run=True)
    assert res["count"] == 2
    assert "com.apple.TimeMachine.1" in res["snapshots"]

def test_clean_snapshots_real(monkeypatch):
    mock_snaps = [{"name": "com.apple.TimeMachine.1", "date": "1"}]
    monkeypatch.setattr(cleaner.snapshots, "list_snapshots", lambda: mock_snaps)
    
    # Mock delete_snapshot
    monkeypatch.setattr(cleaner.snapshots, "delete_snapshot", lambda name: (True, "Deleted"))
    
    res = clean_snapshots(dry_run=False)
    assert res["deleted"] == 1
    assert res["failed"] == 0

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

def test_clean_snapshots_clamps_negative_delta(monkeypatch):
    monkeypatch.setattr("cleaner.snapshots.list_snapshots",
                        lambda: [{"name": "com.apple.TimeMachine.2026-07-01-120000.local"}])
    monkeypatch.setattr("cleaner.snapshots.delete_all_snapshots",
                        lambda: (["Deleted snapshot: x"], []))
    frees = iter([100_500, 100_000])  # disk got FULLER during deletion

    class FakeUsage:
        def __init__(self, free):
            self.free = free

    monkeypatch.setattr("cleaner.snapshots.shutil.disk_usage",
                        lambda _: FakeUsage(next(frees)))
    result = clean_snapshots(dry_run=False)
    assert result["reclaimed_bytes"] == 0
