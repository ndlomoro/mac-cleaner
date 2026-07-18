import pytest
from pathlib import Path
import subprocess
from utils.helpers import (
    run_command,
    format_size,
    get_dir_size,
    get_file_hash,
    file_age_days,
    get_disk_usage,
    get_app_list,
)

def test_format_size():
    assert format_size(0) == "0 B"
    assert format_size(500) == "500 B"
    assert format_size(1000) == "1.00 KB"
    assert format_size(1500) == "1.50 KB"
    assert format_size(1000000) == "1.00 MB"
    assert format_size(1000000000) == "1.00 GB"
    assert format_size(1000000000000) == "1.00 TB"

def test_run_command_success():
    stdout, stderr, rc = run_command(["echo", "hello"])
    assert rc == 0
    assert stdout.strip() == "hello"
    assert stderr == ""

def test_run_command_failure():
    stdout, stderr, rc = run_command(["nonexistent_command_xyz"])
    assert rc == -1
    assert "No such file or directory" in stderr

def test_get_dir_size(tmp_path):
    assert get_dir_size(tmp_path / "nonexistent") == 0
    
    # Create files
    file1 = tmp_path / "f1.txt"
    file1.write_bytes(b"hello")  # 5 bytes
    
    file2 = tmp_path / "sub" / "f2.txt"
    file2.parent.mkdir()
    file2.write_bytes(b"world123")  # 8 bytes
    
    assert get_dir_size(tmp_path) == 13

def test_get_file_hash(tmp_path):
    file = tmp_path / "hash.txt"
    file.write_bytes(b"hello world")
    
    import hashlib
    expected = hashlib.md5(b"hello world").hexdigest()
    assert get_file_hash(file) == expected
    assert get_file_hash(tmp_path / "nonexistent") == ""

def test_file_age_days(tmp_path):
    file = tmp_path / "age.txt"
    file.write_bytes(b"temp")
    
    import time
    # Set modify time to 2 days ago
    two_days_ago = time.time() - (2 * 86400)
    import os
    os.utime(file, (two_days_ago, two_days_ago))
    
    age = file_age_days(file)
    assert pytest.approx(age, 0.1) == 2.0
    assert file_age_days(tmp_path / "nonexistent") == 0

def test_get_disk_usage():
    usage = get_disk_usage()
    assert "total" in usage
    assert "used" in usage
    assert "free" in usage
    assert "percent" in usage
    assert usage["total"] > 0

def test_get_app_list(monkeypatch):
    # Mock Path.exists and glob for /Applications
    # to avoid scanning the real /Applications during tests.
    class MockAppPath:
        def __init__(self, name):
            self.name = name
        def exists(self):
            return True
        def glob(self, pattern):
            return [Path(f"/Applications/{self.name}")]
            
    # We can just check the function runs and returns list or empty
    apps = get_app_list()
    assert isinstance(apps, list)
