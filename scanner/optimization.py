"""Mac optimization scanner - checks launch agents."""
from pathlib import Path

def check_launch_agents() -> list[dict]:
    """Check user launch agents and daemons for disabled/suspicious ones."""
    agents = []
    user_agents_dir = Path.home() / "Library" / "LaunchAgents"
    system_agents_dir = Path("/Library/LaunchAgents")
    system_daemons_dir = Path("/Library/LaunchDaemons")

    for agent_dir in [user_agents_dir, system_agents_dir, system_daemons_dir]:
        if not agent_dir.exists():
            continue
        try:
            for plist in agent_dir.glob("*.plist"):
                agents.append({
                    "name": plist.stem,
                    "path": str(plist),
                    "location": agent_dir.name,
                    "user_owned": "user" in str(agent_dir).lower(),
                })
        except (OSError, PermissionError):
            pass

    return agents
