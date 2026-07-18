"""Dashboard - disk usage + feature areas. Number keys navigate."""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from utils.helpers import format_size, get_disk_usage

AREAS = [
    ("1", "System Data (Junk)", "junk", "SAFE"),
    ("2", "Space Finder", "space_finder", "RISKY"),
    ("3", "Privacy", "privacy", "SAFE/RISKY"),
    ("4", "Optimize", "optimize", "SAFE"),
    ("5", "Snapshots", "snapshots", "RISKY"),
    ("6", "Uninstall Apps", "uninstall", "CAUTION"),
]


class DashboardScreen(Screen):
    BINDINGS = [(key, f"goto('{screen}')", label)
                for key, label, screen, _ in AREAS]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Static(id="disk")
            table = DataTable(id="areas", cursor_type="row")
            yield table
        yield Footer()

    def on_mount(self) -> None:
        usage = get_disk_usage()
        self.query_one("#disk", Static).update(
            f"Disk: {format_size(usage['free'])} free of "
            f"{format_size(usage['total'])} ({usage['percent']:.0f}% used)")
        table = self.query_one(DataTable)
        table.add_columns("Key", "Area", "Levels")
        for key, label, _, levels in AREAS:
            table.add_row(key, label, levels)

    def action_goto(self, screen: str) -> None:
        self.app.push_screen(screen)
