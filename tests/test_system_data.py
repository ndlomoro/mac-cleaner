import pytest
from pathlib import Path
import scanner.system_data
import cleaner.system_data
from scanner.system_data import ScanResult, scan_all
from cleaner.system_data import clean_system_data

def test_scan_result_add_file():
    res = ScanResult("test_cat", "Test Category")
    assert res.category == "test_cat"
    assert res.name == "Test Category"
    assert res.total_size == 0
    assert res.file_count == 0
    
    res.add_file("/path/to/file.txt", 100, 5)
    assert res.total_size == 100
    assert res.file_count == 1
    assert res.files[0]["path"] == "/path/to/file.txt"
    assert res.files[0]["size"] == 100
    assert res.files[0]["age_days"] == 5
    assert res.human_size == "100 B"

def test_system_data_scan_and_clean(tmp_path, monkeypatch):
    # Setup mock directories
    cache_dir = tmp_path / "Caches"
    cache_dir.mkdir()
    log_dir = tmp_path / "Logs"
    log_dir.mkdir()
    downloads_dir = tmp_path / "Downloads"
    downloads_dir.mkdir()
    
    # Create test files in mock directories
    # 1. Caches - old cache file (10 days old)
    old_cache = cache_dir / "old_cache.txt"
    old_cache.write_bytes(b"a" * 50)
    
    # 2. Caches - new cache file (1 day old)
    new_cache = cache_dir / "new_cache.txt"
    new_cache.write_bytes(b"b" * 20)
    
    # 3. Logs - old log file (35 days old)
    old_log = log_dir / "system.log"
    old_log.write_bytes(b"log_data")
    
    # Set file ages (utime mtime)
    import time
    import os
    now = time.time()
    os.utime(old_cache, (now - 10 * 86400, now - 10 * 86400))
    os.utime(new_cache, (now - 1 * 86400, now - 1 * 86400))
    os.utime(old_log, (now - 35 * 86400, now - 35 * 86400))
    
    # Monkeypatch CACHE_DIRS and LOG_DIRS in scanner.system_data
    monkeypatch.setattr(scanner.system_data, "CACHE_DIRS", [cache_dir])
    monkeypatch.setattr(scanner.system_data, "LOG_DIRS", [log_dir])
    monkeypatch.setattr(scanner.system_data, "HOME", tmp_path)
    
    # Let's run scan_all with custom age thresholds
    results = scan_all(min_cache_age=7, min_log_age=30, min_download_age=90)
    
    # Verify scanner results
    assert len(results) >= 2  # caches and logs should be present
    
    cache_res = next(r for r in results if r.category == "caches")
    assert cache_res.file_count == 1
    assert Path(cache_res.files[0]["path"]).name == "old_cache.txt"
    
    log_res = next(r for r in results if r.category == "logs")
    assert log_res.file_count == 1
    assert Path(log_res.files[0]["path"]).name == "system.log"
    
    # Now let's test cleaner (dry run first)
    monkeypatch.setattr(cleaner.system_data, "scan_all", lambda: results)
    
    cleanup_dry = clean_system_data(dry_run=True)
    assert "User Caches" in cleanup_dry
    assert cleanup_dry["User Caches"]["deleted"] == 1
    assert cleanup_dry["User Caches"]["freed_bytes"] == 50
    assert old_cache.exists()  # dry run shouldn't delete file
    
    # Test cleaner (actual run)
    # Mock send2trash to delete file
    import send2trash
    # We can use actual pathlib or send2trash if we want, or mock it to ensure it gets called.
    # Let's mock send2trash to actually delete the file for ease of test assert.
    def mock_send2trash(path):
        Path(path).unlink()
    
    monkeypatch.setattr(cleaner.system_data, "send2trash", mock_send2trash)
    
    cleanup_real = clean_system_data(dry_run=False)
    assert cleanup_real["User Caches"]["deleted"] == 1
    assert not old_cache.exists()  # should be deleted/trashed now
