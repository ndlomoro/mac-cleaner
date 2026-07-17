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
