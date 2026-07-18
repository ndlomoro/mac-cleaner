import pytest
from pathlib import Path
from scanner.large_files import find_large_files, LargeFile

def test_find_large_files(tmp_path, monkeypatch):
    """Test that the large file scanner correctly identifies files over the threshold."""
    # Setup test files
    small_file = tmp_path / "small.txt"
    small_file.write_bytes(b"x" * 1024)  # 1 KB

    large_file = tmp_path / "large.dmg"
    large_file.write_bytes(b"y" * (2 * 1024 * 1024))  # 2 MB

    # Mock SCAN_DIRS to only scan our tmp_path
    import scanner.large_files
    monkeypatch.setattr(scanner.large_files, "SCAN_DIRS", [tmp_path])

    # Run scanner looking for >1MB
    results = find_large_files(min_size_mb=1.0)

    assert len(results) == 1
    assert results[0].path == str(large_file)
    assert results[0].size == 2 * 1024 * 1024

def test_find_large_files_skips_extensions(tmp_path, monkeypatch):
    """Test that skipped extensions are ignored even if they are large."""
    # This extension is in SKIP_EXTENSIONS (.log is not, but .txt is)
    large_txt = tmp_path / "large_file.txt"
    large_txt.write_bytes(b"y" * (2 * 1024 * 1024))  # 2 MB

    import scanner.large_files
    monkeypatch.setattr(scanner.large_files, "SCAN_DIRS", [tmp_path])

    results = find_large_files(min_size_mb=1.0)

    # Should be empty because .txt is skipped
    assert len(results) == 0


import core.deleter as deleter_mod
from core.deleter import DeleteReport
from cleaner.large_files import clean_large_files


def test_clean_large_files_via_safe_delete(tmp_path, monkeypatch):
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir()

    def _fake(path):
        dest = trash_dir / path.name
        path.rename(dest)
        return dest

    monkeypatch.setattr(deleter_mod, "trash_item", _fake)
    monkeypatch.setattr(deleter_mod, "running_apps", lambda: {})

    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * 100)

    report_dry = clean_large_files([str(big)], dry_run=True)
    assert isinstance(report_dry, DeleteReport)
    assert big.exists()
    assert report_dry.trashed_bytes == 100

    report = clean_large_files([str(big)], dry_run=False)
    assert not big.exists()
    assert (trash_dir / "big.bin").exists()
    assert report.category == "large_files"


def test_clean_large_files_hard_protected_still_skipped(monkeypatch, no_running_apps):
    from pathlib import Path as P
    key = P.home() / ".ssh" / "id_ed25519"
    report = clean_large_files([str(key)], dry_run=True)
    assert len(report.skipped) == 1
    assert report.skipped[0].reason
