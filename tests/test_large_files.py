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

def test_clean_large_files(tmp_path, monkeypatch):
    from cleaner.large_files import clean_large_files
    
    # Create a test file
    large_dmg = tmp_path / "large.dmg"
    large_dmg.write_bytes(b"y" * 1000)
    
    # Test dry run
    res = clean_large_files([str(large_dmg)], dry_run=True)
    assert res["deleted"] == 1
    assert res["freed_bytes"] == 1000
    assert large_dmg.exists()
    
    # Mock send2trash
    monkeypatch.setattr("cleaner.large_files.send2trash", lambda p: Path(p).unlink())
    
    # Test actual clean
    res2 = clean_large_files([str(large_dmg)], dry_run=False)
    assert res2["deleted"] == 1
    assert res2["freed_bytes"] == 1000
    assert not large_dmg.exists()

