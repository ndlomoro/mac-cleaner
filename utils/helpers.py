"""Core utilities for mac-cleaner."""
import os
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime

HOME = Path.home()
LIBRARY = HOME / "Library"


def run_command(cmd: list[str], sudo: bool = False) -> tuple[str, str, int]:
    """Run a shell command and return (stdout, stderr, returncode)."""
    full_cmd = ["sudo"] + cmd if sudo else cmd
    try:
        result = subprocess.run(
            full_cmd, capture_output=True, text=True, timeout=120
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", -1
    except Exception as e:
        return "", str(e), -1


def format_size(bytes_val: int) -> str:
    """Format bytes to human-readable string (macOS uses base-10/1000)."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(bytes_val) < 1000.0:
            if unit == "B":
                return f"{int(bytes_val)} B"
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1000.0
    return f"{bytes_val:.2f} PB"


def get_dir_size(path: Path) -> int:
    """Get total size of a directory in bytes."""
    total = 0
    if not path.exists():
        return 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass
    return total


def get_file_hash(filepath: Path, chunk_size: int = 8192) -> str:
    """Get MD5 hash of a file for duplicate detection."""
    hasher = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, PermissionError):
        return ""


def file_age_days(filepath: Path) -> int:
    """Get file age in days."""
    try:
        mtime = filepath.stat().st_mtime
        return (datetime.now().timestamp() - mtime) / 86400
    except (OSError, PermissionError):
        return 0


def get_disk_usage() -> dict:
    """Get disk usage statistics."""
    import shutil
    try:
        usage = shutil.disk_usage("/")
        # shutil.disk_usage gives total, used, free in bytes
        # Calculate percentage manually
        pct = int((usage.used / usage.total) * 100) if usage.total > 0 else 0
        return {
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": pct,
        }
    except (OSError, PermissionError):
        return {}


def get_app_list() -> list[dict]:
    """Get list of installed applications with size and install date."""
    apps = []
    apps_dir = Path("/Applications")
    if not apps_dir.exists():
        return apps
    for app in apps_dir.glob("*.app"):
        try:
            size = get_dir_size(app)
            mtime = app.stat().st_mtime
            install_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            apps.append({
                "name": app.name.replace(".app", ""),
                "path": str(app),
                "size": size,
                "install_date": install_date,
            })
        except (OSError, PermissionError):
            pass
    apps.sort(key=lambda x: x["size"], reverse=True)
    return apps
