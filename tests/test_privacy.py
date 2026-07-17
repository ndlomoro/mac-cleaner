import pytest
from pathlib import Path
import scanner.privacy
import cleaner.privacy
from scanner.privacy import scan_browser_data, scan_tracking_data, scan_recently_used
from cleaner.privacy import clean_privacy

def test_scan_and_clean_privacy(tmp_path, monkeypatch):
    # Setup mock browser & tracking paths
    safari_cache = tmp_path / "com.apple.Safari"
    safari_cache.mkdir()
    safari_cache_file = safari_cache / "cache.db"
    safari_cache_file.write_bytes(b"safari data")
    
    tracking_dir = tmp_path / "DiagnosticReports"
    tracking_dir.mkdir()
    tracking_file = tracking_dir / "report.crash"
    tracking_file.write_bytes(b"crash report")
    
    recent_dir = tmp_path / "Library" / "Preferences"
    recent_dir.mkdir(parents=True, exist_ok=True)
    recent_items = recent_dir / "com.apple.recentitems"
    recent_items.write_text("recent file info")
    
    # Configure mock locations in scanner
    mock_browser_paths = {
        "Safari": {
            "caches": safari_cache
        }
    }
    
    monkeypatch.setattr(scanner.privacy, "BROWSER_PATHS", mock_browser_paths)
    monkeypatch.setattr(scanner.privacy, "TRACKING_PATHS", [tracking_dir])
    monkeypatch.setattr(scanner.privacy, "HOME", tmp_path)
    
    monkeypatch.setattr(cleaner.privacy, "scan_browser_data", lambda: scan_browser_data())
    monkeypatch.setattr(cleaner.privacy, "scan_tracking_data", lambda: scan_tracking_data())
    monkeypatch.setattr(cleaner.privacy, "scan_recently_used", lambda: scan_recently_used())
    
    # Run scans
    browser_data = scan_browser_data()
    assert len(browser_data) == 1
    assert browser_data[0]["browser"] == "Safari"
    assert browser_data[0]["size"] == 11
    
    tracking_data = scan_tracking_data()
    assert len(tracking_data) == 1
    assert tracking_data[0]["type"] == "tracking_dir"
    assert tracking_data[0]["size"] == 12
    
    recent_data = scan_recently_used()
    assert len(recent_data) == 1
    assert recent_data[0]["type"] == "recent_items"
    assert recent_data[0]["size"] == 16
    
    # Test clean - dry run
    res_dry = clean_privacy(dry_run=True)
    assert res_dry["browser_cache"]["deleted"] == 1
    assert res_dry["tracking_data"]["deleted"] == 1
    assert res_dry["recently_used"]["cleared"] == 1
    
    # Confirm files still exist
    assert safari_cache.exists()
    assert tracking_file.exists()
    assert recent_items.read_text() == "recent file info"
    
    # Mock send2trash
    monkeypatch.setattr(cleaner.privacy, "send2trash", lambda p: Path(p).unlink() if Path(p).is_file() else (
        [f.unlink() for f in Path(p).rglob("*") if f.is_file()],
        Path(p).rmdir()
    ))
    
    # Test clean - real
    res_real = clean_privacy(dry_run=False)
    assert res_real["browser_cache"]["deleted"] == 1
    assert res_real["tracking_data"]["deleted"] == 1
    assert res_real["recently_used"]["cleared"] == 1
    
    # Check deletion and clearing
    assert not safari_cache.exists()
    assert not tracking_dir.exists()
    assert recent_items.read_text() == ""
