"""Optimization cleaner - handles brew cleanup, dev caches, and system maintenance."""
import json
from pathlib import Path
from send2trash import send2trash

from utils.helpers import run_command, format_size
from scanner.optimization import check_launch_agents
from utils.logger import log_cleaning_action


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


def run_periodic_scripts(dry_run: bool = False) -> dict:
    """Run macOS daily/weekly/monthly maintenance scripts."""
    if dry_run:
        log_cleaning_action("Would Run Periodic Scripts", "", dry_run=True)
        return {
            "message": "Would run daily/weekly/monthly periodic scripts",
            "dry_run": True,
            "scripts": ["/usr/libexec periodic daily", "/usr/libexec periodic weekly", "/usr/libexec periodic monthly"],
        }

    results = {}
    for period in ["daily", "weekly", "monthly"]:
        stdout, stderr, rc = run_command(
            ["/usr/libexec", "periodic", period],
            sudo=True,
        )
        if rc == 0:
            log_cleaning_action(f"Ran {period} Script", "")
        else:
            log_cleaning_action(f"Failed {period} Script", stderr.strip())
            
        results[period] = {
            "success": rc == 0,
            "output": stdout.strip()[:500] if stdout else "",
            "error": stderr.strip()[:500] if stderr else "",
        }

    return {"periodic_scripts": results}


def clear_xcode_derived_data(dry_run: bool = False) -> dict:
    """Clear Xcode derived data and build caches."""
    derived_data = Path.home() / "Library" / "Developer" / "Xcode" / "DerivedData"
    
    if not derived_data.exists():
        return {"message": "No Xcode derived data found", "skipped": True}

    size = sum(f.stat().st_size for f in derived_data.rglob("*") if f.is_file())

    if dry_run:
        log_cleaning_action("Would Trash Xcode DerivedData", str(derived_data), dry_run=True)
        return {
            "message": f"Xcode DerivedData: {format_size(size)} ready to clear",
            "size": size,
            "dry_run": True,
        }

    try:
        send2trash(derived_data)
        log_cleaning_action("Trashed Xcode DerivedData", str(derived_data))
        return {"message": f"Cleared Xcode DerivedData ({format_size(size)})", "freed": size}
    except Exception as e:
        log_cleaning_action("Failed to Trash Xcode DerivedData", str(e))
        return {"message": "Failed to clear Xcode data", "error": str(e)}


def clear_cocoapods_cache(dry_run: bool = False) -> dict:
    """Clear CocoaPods cache."""
    pods_cache = Path.home() / ".cocoapods"

    if not pods_cache.exists():
        return {"message": "No CocoaPods cache found", "skipped": True}

    size = sum(f.stat().st_size for f in pods_cache.rglob("*") if f.is_file())

    if dry_run:
        log_cleaning_action("Would Trash CocoaPods Cache", str(pods_cache), dry_run=True)
        return {
            "message": f"CocoaPods cache: {format_size(size)} ready to clear",
            "size": size,
            "dry_run": True,
        }

    try:
        send2trash(pods_cache)
        log_cleaning_action("Trashed CocoaPods Cache", str(pods_cache))
        return {"message": f"Cleared CocoaPods cache ({format_size(size)})", "freed": size}
    except Exception as e:
        log_cleaning_action("Failed to Trash CocoaPods Cache", str(e))
        return {"message": "Failed to clear CocoaPods cache", "error": str(e)}


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


def clear_pip_cache(dry_run: bool = False) -> dict:
    """Clear pip cache."""
    pip_cache = Path.home() / "Library" / "Caches" / "pip"

    if not pip_cache.exists():
        return {"message": "No pip cache found", "skipped": True}

    size = sum(f.stat().st_size for f in pip_cache.rglob("*") if f.is_file())

    if dry_run:
        log_cleaning_action("Would Trash Pip Cache", str(pip_cache), dry_run=True)
        return {
            "message": f"pip cache: {format_size(size)} ready to clear",
            "size": size,
            "dry_run": True,
        }

    try:
        send2trash(pip_cache)
        log_cleaning_action("Trashed Pip Cache", str(pip_cache))
        return {"message": f"Cleared pip cache ({format_size(size)})", "freed": size}
    except Exception as e:
        log_cleaning_action("Failed Pip Cache", str(e))
        return {"message": "Failed to clear pip cache", "error": str(e)}


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
