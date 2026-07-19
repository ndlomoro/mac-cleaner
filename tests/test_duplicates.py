import pytest
from pathlib import Path
import scanner.duplicates
from scanner.duplicates import find_duplicates, _file_hash, _partial_hash

def test_file_hash(tmp_path):
    file1 = tmp_path / "file1.bin"
    file1.write_bytes(b"duplicate content")

    h1 = _file_hash(file1)
    assert len(h1) == 32
    assert _file_hash(tmp_path / "nonexistent") == ""


def test_partial_hash(tmp_path):
    file1 = tmp_path / "file1.bin"
    file1.write_bytes(b"duplicate content")

    h1 = _partial_hash(file1)
    assert len(h1) == 32
    assert _partial_hash(tmp_path / "nonexistent") == ""


def test_find_duplicates(tmp_path, monkeypatch):
    # Setup folders
    dir1 = tmp_path / "Documents"
    dir1.mkdir()

    # Create duplicate files (>= 1MB threshold)
    f1 = dir1 / "f1.bin"
    f1.write_bytes(b"x" * 1_000_000)

    f2 = dir1 / "f2.bin"
    f2.write_bytes(b"x" * 1_000_000)

    # Unique file (same size, different content)
    f3 = dir1 / "f3.bin"
    f3.write_bytes(b"y" * 1_000_000)

    # Too small duplicate files (< 1MB threshold)
    f4 = dir1 / "f4.bin"
    f4.write_bytes(b"small")
    f5 = dir1 / "f5.bin"
    f5.write_bytes(b"small")

    # Set SCAN_DIRS to scan our tmp_path
    monkeypatch.setattr(scanner.duplicates, "SCAN_DIRS", [dir1])

    duplicates = find_duplicates()

    assert len(duplicates) == 1
    dup_group = duplicates[0]
    assert dup_group["size"] == 1_000_000
    assert len(dup_group["files"]) == 2
    assert str(f1) in dup_group["files"]
    assert str(f2) in dup_group["files"]
    assert dup_group["wasted"] == dup_group["size"]


def test_find_duplicates_excludes_photoslibrary(tmp_path, monkeypatch):
    """.photoslibrary contents are hard-protected and can never be deleted -
    hashing them wastes hours and yields dead rows (never-actionable groups)."""
    dir1 = tmp_path / "Pictures"
    dir1.mkdir()

    lib = dir1 / "Photos Library.photoslibrary"
    (lib / "originals").mkdir(parents=True)
    inner1 = lib / "originals" / "inner1.bin"
    inner1.write_bytes(b"a" * 1_000_000)
    inner2 = lib / "originals" / "inner2.bin"
    inner2.write_bytes(b"a" * 1_000_000)

    # A normal (non-library) duplicate pair, which must still be found.
    normal1 = dir1 / "normal1.bin"
    normal1.write_bytes(b"b" * 1_000_000)
    normal2 = dir1 / "normal2.bin"
    normal2.write_bytes(b"b" * 1_000_000)

    monkeypatch.setattr(scanner.duplicates, "SCAN_DIRS", [dir1])

    duplicates = find_duplicates()

    assert len(duplicates) == 1
    dup_group = duplicates[0]
    assert str(normal1) in dup_group["files"]
    assert str(normal2) in dup_group["files"]
    assert str(inner1) not in dup_group["files"]
    assert str(inner2) not in dup_group["files"]


def test_find_duplicates_only_full_hashes_partial_survivors(tmp_path, monkeypatch):
    """3 same-size files; only 2 share the first 64KB. Full hash must be
    called exactly twice (the stage-2 survivors), never on the divergent
    third file."""
    dir1 = tmp_path / "Documents"
    dir1.mkdir()

    size = 1_000_000
    prefix = b"p" * 65536

    f1 = dir1 / "f1.bin"
    f1.write_bytes(prefix + b"tail-A" * ((size - len(prefix)) // 6))

    f2 = dir1 / "f2.bin"
    f2.write_bytes(prefix + b"tail-A" * ((size - len(prefix)) // 6))

    # Same size as f1/f2, but diverges within the first 64KB.
    f3 = dir1 / "f3.bin"
    divergent_prefix = b"q" * 65536
    f3.write_bytes(divergent_prefix + b"tail-A" * ((size - len(divergent_prefix)) // 6))

    # Pad all three to the exact same size.
    for f in (f1, f2, f3):
        with open(f, "ab") as fh:
            remaining = size - f.stat().st_size
            if remaining > 0:
                fh.write(b"z" * remaining)

    assert f1.stat().st_size == f2.stat().st_size == f3.stat().st_size == size

    monkeypatch.setattr(scanner.duplicates, "SCAN_DIRS", [dir1])

    call_count = 0
    real_file_hash = scanner.duplicates._file_hash

    def counting_file_hash(path, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        return real_file_hash(path, *args, **kwargs)

    monkeypatch.setattr(scanner.duplicates, "_file_hash", counting_file_hash)

    duplicates = find_duplicates()

    assert call_count == 2
    assert len(duplicates) == 1
    dup_group = duplicates[0]
    assert str(f1) in dup_group["files"]
    assert str(f2) in dup_group["files"]
    assert str(f3) not in dup_group["files"]


def test_find_duplicates_shared_prefix_divergent_tail_not_grouped(tmp_path, monkeypatch):
    """Files larger than 64KB with an identical first 65536 bytes but a
    different tail must NOT be grouped as duplicates."""
    dir1 = tmp_path / "Documents"
    dir1.mkdir()

    size = 1_000_000
    shared_prefix = b"s" * 65536

    f1 = dir1 / "f1.bin"
    f1.write_bytes(shared_prefix + b"A" * (size - len(shared_prefix)))

    f2 = dir1 / "f2.bin"
    f2.write_bytes(shared_prefix + b"B" * (size - len(shared_prefix)))

    assert f1.stat().st_size == f2.stat().st_size == size

    monkeypatch.setattr(scanner.duplicates, "SCAN_DIRS", [dir1])

    duplicates = find_duplicates()

    assert duplicates == []


def test_find_duplicates_1mb_floor_boundary(tmp_path, monkeypatch):
    """Default floor is 1_000_000 bytes: a 999_999-byte duplicate pair is
    ignored, but a 1_000_000-byte duplicate pair is found."""
    dir1 = tmp_path / "Documents"
    dir1.mkdir()

    below = dir1 / "below1.bin"
    below.write_bytes(b"n" * 999_999)
    below2 = dir1 / "below2.bin"
    below2.write_bytes(b"n" * 999_999)

    at_floor = dir1 / "at1.bin"
    at_floor.write_bytes(b"m" * 1_000_000)
    at_floor2 = dir1 / "at2.bin"
    at_floor2.write_bytes(b"m" * 1_000_000)

    monkeypatch.setattr(scanner.duplicates, "SCAN_DIRS", [dir1])

    duplicates = find_duplicates()

    assert len(duplicates) == 1
    dup_group = duplicates[0]
    assert dup_group["size"] == 1_000_000
    assert str(at_floor) in dup_group["files"]
    assert str(at_floor2) in dup_group["files"]
    assert str(below) not in dup_group["files"]
    assert str(below2) not in dup_group["files"]
