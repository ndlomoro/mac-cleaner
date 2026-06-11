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
