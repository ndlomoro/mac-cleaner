"""Time Machine local snapshot manager."""
from utils.helpers import run_command

def list_snapshots() -> list[dict]:
    """List all local Time Machine snapshots."""
    stdout, stderr, rc = run_command(
        ["tmutil", "listlocalsnapshots", "/"]
    )
    if rc != 0:
        return []

    snapshots = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if line and line.startswith("com.apple"):
            snapshots.append({
                "name": line,
                "date": line.split("update-")[-1] if "update-" in line else line,
            })
    return snapshots
