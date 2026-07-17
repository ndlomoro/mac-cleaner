import pytest
from pathlib import Path
import scanner.duplicates
from scanner.duplicates import find_duplicates, _file_hash

def test_file_hash(tmp_path):
    file1 = tmp_path / "file1.bin"
    file1.write_bytes(b"duplicate content")
    
    h1 = _file_hash(file1)
    assert len(h1) == 32
    assert _file_hash(tmp_path / "nonexistent") == ""

def test_find_duplicates(tmp_path, monkeypatch):
    # Setup folders
    dir1 = tmp_path / "Documents"
    dir1.mkdir()
    
    # Create duplicate files
    f1 = dir1 / "f1.bin"
    f1.write_bytes(b"same content" * 1000)  # > 10240 bytes threshold
    
    f2 = dir1 / "f2.bin"
    f2.write_bytes(b"same content" * 1000)
    
    # Unique file
    f3 = dir1 / "f3.bin"
    f3.write_bytes(b"different content" * 1000)
    
    # Too small duplicate files (< 10240 bytes)
    f4 = dir1 / "f4.bin"
    f4.write_bytes(b"small")
    f5 = dir1 / "f5.bin"
    f5.write_bytes(b"small")
    
    # Set SCAN_DIRS to scan our tmp_path
    monkeypatch.setattr(scanner.duplicates, "SCAN_DIRS", [dir1])
    
    duplicates = find_duplicates(min_size_bytes=10240)
    
    assert len(duplicates) == 1
    dup_group = duplicates[0]
    assert dup_group["size"] == len(b"same content" * 1000)
    assert len(dup_group["files"]) == 2
    assert str(f1) in dup_group["files"]
    assert str(f2) in dup_group["files"]
    assert dup_group["wasted"] == dup_group["size"]
