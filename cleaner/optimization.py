"""Optimization cleaner - handles brew cleanup, dev caches, and system maintenance."""
from pathlib import Path

from core.deleter import DeleteReport, safe_delete
from utils.helpers import run_command, get_dir_size
from scanner.optimization import check_launch_agents
from utils.logger import log_cleaning_action

DERIVED_DATA = Path.home() / "Library" / "Developer" / "Xcode" / "DerivedData"
PODS_CACHE = Path.home() / ".cocoapods"
PIP_CACHE = Path.home() / "Library" / "Caches" / "pip"


def run_brew_cleanup(dry_run: bool = False) -> dict:
    """Run Homebrew cleanup if brew is installed."""
    _, _, rc = run_command(["which", "brew"])
    if rc != 0:
        return {"message": "Homebrew not installed, skipping", "skipped": True}

    if dry_run:
        stdout, _, _ = run_command(["brew", "cleanup", "-n"])
        log_cleaning_action("Would Cleanup Brew", "", dry_run=True)
        return {
            "message": "Homebrew cleanup (dry run)",
            "would_clean": stdout.strip() if stdout else "Nothing to clean",
            "dry_run": True,
        }

    stdout, stderr, rc = run_command(["brew", "cleanup", "-s"])
    if rc == 0:
        log_cleaning_action("Cleaned Brew", "")
        return {"message": "Homebrew cleanup complete", "output": stdout.strip()}
    log_cleaning_action("Failed Brew Cleanup", stderr.strip())
    return {"message": "Homebrew cleanup failed", "error": stderr.strip()}


def _clear_cache_dir(path: Path, category: str, dry_run: bool) -> DeleteReport | dict:
    if not path.exists():
        return {"message": f"No {category} found", "skipped": True}
    items = [{"path": str(path), "size": get_dir_size(path)}]
    return safe_delete(items, category, dry_run=dry_run)


def clear_xcode_derived_data(dry_run: bool = False) -> DeleteReport | dict:
    return _clear_cache_dir(DERIVED_DATA, "xcode_derived_data", dry_run)


def clear_cocoapods_cache(dry_run: bool = False) -> DeleteReport | dict:
    return _clear_cache_dir(PODS_CACHE, "cocoapods_cache", dry_run)


def clear_npm_cache(dry_run: bool = False) -> dict:
    """Clear npm cache."""
    if dry_run:
        stdout, _, rc = run_command(["npm", "cache", "clean", "--dry-run"])
        if rc != 0:
            return {"message": "npm not installed or no cache", "skipped": True}
        log_cleaning_action("Would Clear NPM Cache", "", dry_run=True)
        return {"message": "npm cache cleanup (dry run)", "dry_run": True}

    _, stderr, rc = run_command(["npm", "cache", "clean", "--force"])
    if rc == 0:
        log_cleaning_action("Cleared NPM Cache", "")
        return {"message": "npm cache cleaned"}
    log_cleaning_action("Failed NPM Cache", stderr.strip())
    return {"message": "npm cache cleanup failed or npm not installed", "skipped": True}


def clear_pip_cache(dry_run: bool = False) -> DeleteReport | dict:
    return _clear_cache_dir(PIP_CACHE, "pip_cache", dry_run)


def optimize_mac(dry_run: bool = False) -> dict:
    """Run all optimization tasks."""
    return {
        "launch_agents": {"count": len(check_launch_agents())},
        "brew_cleanup": run_brew_cleanup(dry_run=dry_run),
        "xcode_derived_data": clear_xcode_derived_data(dry_run=dry_run),
        "cocoapods_cache": clear_cocoapods_cache(dry_run=dry_run),
        "npm_cache": clear_npm_cache(dry_run=dry_run),
        "pip_cache": clear_pip_cache(dry_run=dry_run),
    }
