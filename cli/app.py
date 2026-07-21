"""The interactive menu loop - the primary UI.

Launch with `python main.py`. A live disk header sits above a numbered menu;
each choice runs one flow (see cli/flows.py) and returns here. A flow that
raises is caught so a single failure never drops the whole session.
"""
from cli import flows
from cli.io import UI
from cli.render import disk_panel

# (key, title, hint, handler_name). Handlers are resolved by name from
# cli.flows at dispatch time - late binding keeps them monkeypatchable.
MENU = [
    ("1", "Quick Scan", "all categories, read-only", "quick_scan"),
    ("2", "System Junk", "caches, logs, temp, mail  [SAFE]", "system_junk"),
    ("3", "Space Finder", "large files, duplicates, downloads, iOS backups",
     "space_finder"),
    ("4", "Privacy", "browser & tracking data", "privacy"),
    ("5", "Optimize", "developer caches, brew/npm", "optimize"),
    ("6", "Snapshots", "local Time Machine  [CAUTION]", "snapshots"),
    ("7", "Uninstall App", "app bundle + leftovers", "uninstall"),
    ("8", "Dev Junk", "node_modules, builds, docker, simulators", "dev_junk"),
]


def run(ui: "UI | None" = None) -> None:
    ui = ui or UI()
    handlers = {key: name for key, _, _, name in MENU}
    choices = [key for key, *_ in MENU] + ["q"]
    while True:
        ui.print()
        ui.print(disk_panel())
        for key, title, hint, _ in MENU:
            ui.print(f"  [bold]{key}[/bold]  {title:<14}[dim]{hint}[/dim]")
        ui.print("  [bold]q[/bold]  Quit")
        choice = ui.choose("Select", choices)
        if choice == "q":
            ui.print("Bye.")
            return
        try:
            getattr(flows, handlers[choice])(ui)
        except Exception as e:  # noqa: BLE001 - boundary: a flow error must
            # never kill the menu; report it and return to the menu.
            ui.print(f"[red]Something went wrong: {e}[/red]")
        ui.pause()
