"""Dashboard - disk usage + feature areas. Number keys navigate."""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from scanner.system_data import scan_all, scan_space_finder
from ui.screens._util import run_offthread, skip_resume_rescan
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
                for key, label, screen, _ in AREAS] + [
        ("s", "quick_scan", "Quick Scan"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Static(id="disk")
            table = DataTable(id="areas", cursor_type="row")
            yield table
            yield Static(id="summary")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Key", "Area", "Levels")
        for key, label, _, levels in AREAS:
            table.add_row(key, label, levels)
        self._scanning = False
        self._refresh_disk()

    def _refresh_disk(self) -> None:
        usage = get_disk_usage()
        if not usage:
            self.query_one("#disk", Static).update("Disk: unavailable")
        else:
            free = usage.get("free", 0)
            total = usage.get("total", 0)
            percent = usage.get("percent", 0)
            self.query_one("#disk", Static).update(
                f"Disk: {format_size(free)} free of "
                f"{format_size(total)} ({percent:.0f}% used)")

    def on_screen_resume(self) -> None:
        # Disk line only - re-running the (potentially slow) Quick Scan on
        # every return to the dashboard would be surprising; that stays
        # explicit via the "s" binding.
        if skip_resume_rescan(self) or self._scanning:
            return
        self._refresh_disk()

    def action_goto(self, screen: str) -> None:
        self.app.push_screen(screen)

    def action_quick_scan(self) -> None:
        if self._scanning:
            self.notify("Already scanning…")
            return
        self._scanning = True
        self.query_one("#summary", Static).update("Scanning…")

        def _work():
            return scan_all() + scan_space_finder()

        def _done(results) -> None:
            self._scanning = False
            lines = [
                f"{r.name}: {r.file_count} items (~{r.human_size})"
                for r in results if r.file_count > 0
            ]
            if lines:
                lines.append("[dim]Open an area (1-6) to review and clean.[/dim]")
                text = "\n".join(lines)
            else:
                text = "Nothing found - looking clean."
            self.query_one("#summary", Static).update(text)

        def _error(e: Exception) -> None:
            self._scanning = False
            self.notify(f"Scan failed: {e}", severity="error")

        run_offthread(self, _work, _done, _error)
