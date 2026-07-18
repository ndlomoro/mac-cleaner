"""Snapshot cleaner - removes local Time Machine snapshots."""
import shutil
from scanner.snapshots import list_snapshots
from utils.helpers import format_size, run_command
from utils.logger import log_cleaning_action

def delete_snapshot(name: str) -> tuple[bool, str]:
    """Delete a local snapshot by name. Returns (success, message)."""
    snap_name = name.split("/")[-1].strip()
    stdout, stderr, rc = run_command(
        ["-n", "tmutil", "deletelocalsnapshots", snap_name],
        sudo=True,
    )
    if rc == 0:
        log_cleaning_action("Deleted Snapshot", snap_name)
        return True, f"Deleted snapshot: {snap_name}"
    log_cleaning_action("Failed to Delete Snapshot", f"{snap_name} ({stderr.strip()})")
    return False, f"Failed: {stderr.strip()}"

def delete_all_snapshots() -> tuple[list[str], list[str]]:
    """Delete all local snapshots. Returns (successes, failures)."""
    snapshots = list_snapshots()
    successes = []
    failures = []
    for snap in snapshots:
        success, msg = delete_snapshot(snap["name"])
        if success:
            successes.append(msg)
        else:
            failures.append(msg)
    return successes, failures

def clean_snapshots(dry_run: bool = False) -> dict:
    """Clean local snapshots. Returns cleanup report."""
    snapshots = list_snapshots()
    if not snapshots:
        return {"message": "No local snapshots found", "count": 0}

    if dry_run:
        for snap in snapshots:
            log_cleaning_action("Would Delete Snapshot", snap["name"], dry_run=True)
        return {
            "message": f"Found {len(snapshots)} snapshot(s) ready to delete",
            "count": len(snapshots),
            "snapshots": [s["name"] for s in snapshots],
        }

    free_before = shutil.disk_usage("/").free
    successes, failures = delete_all_snapshots()
    free_after = shutil.disk_usage("/").free
    return {
        "deleted": len(successes),
        "failed": len(failures),
        "successes": successes,
        "failures": failures,
        "reclaimed_bytes": max(0, free_after - free_before),
    }
