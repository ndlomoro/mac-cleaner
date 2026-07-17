import pytest
from pathlib import Path
import scanner.system_data
import cleaner.system_data
from scanner.system_data import ScanResult, scan_all, scan_downloads, scan_space_finder
import core.deleter as deleter_mod
from cleaner.system_data import clean_files, clean_system_data

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


def test_scan_all_returns_only_junk_categories(monkeypatch, tmp_path):
    # scan_all must never return user-data categories.
    # Uses isolated tmp dirs instead of real filesystem roots: an unmocked
    # scan_all() walks /private/var/folders (system-wide temp for every
    # process) and ~/Library/Caches, which is prohibitively slow/unbounded
    # on a real machine. Same property under test, isolated inputs.
    cache_dir = tmp_path / "Caches"
    cache_dir.mkdir()
    (cache_dir / "old.cache").write_bytes(b"x")
    log_dir = tmp_path / "Logs"
    log_dir.mkdir()
    (log_dir / "app.log").write_bytes(b"y")
    monkeypatch.setattr("scanner.system_data.CACHE_DIRS", [cache_dir])
    monkeypatch.setattr("scanner.system_data.LOG_DIRS", [log_dir])
    results = scan_all(min_cache_age=0, min_log_age=0)
    categories = {r.category for r in results}
    assert categories
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
