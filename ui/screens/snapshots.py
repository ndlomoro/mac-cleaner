"""Snapshots screen - Irreversible Action; reports actually-Reclaimed space."""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from cleaner.snapshots import clean_snapshots
from scanner.snapshots import list_snapshots
from ui.screens._util import run_offthread
from ui.widgets.category_header import CategoryHeader
from ui.widgets.gates import TypedGateModal
from utils.helpers import format_size


class SnapshotsScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("x", "delete_all", "Delete All Snapshots"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield CategoryHeader("snapshots")
            yield Static(id="snap-list")
            yield Static(id="snap-log")
        yield Footer()

    def on_mount(self) -> None:
        self.snapshots = []
        run_offthread(self, list_snapshots, self._show, self._load_error)

    def _load_error(self, exc: Exception) -> None:
        self.notify(f"Failed to list snapshots: {exc}", severity="error")

    def _show(self, snaps) -> None:
        self.snapshots = snaps
        listing = "\n".join(s.get("name", "?") for s in snaps) or "No snapshots found."
        self.query_one("#snap-list", Static).update(listing)

    def action_delete_all(self) -> None:
        if not self.snapshots:
            self.notify("No snapshots to delete.")
            return

        def _resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self.notify("Snapshots kept.")
                return
            run_offthread(self, lambda: clean_snapshots(dry_run=False),
                          self._report, self._delete_error)

        self.app.push_screen(
            TypedGateModal(f"Deleting {len(self.snapshots)} snapshot(s)"),
            _resolved,
        )

    def _delete_error(self, exc: Exception) -> None:
        self.notify(f"Failed to delete snapshots: {exc}", severity="error")

    def _report(self, result: dict) -> None:
        reclaimed = result.get("reclaimed_bytes", 0)
        space = (f"Reclaimed ~{format_size(reclaimed)}" if reclaimed
                 else "Reclaimed: unknown (couldn't isolate the freed space)")
        self.query_one("#snap-log", Static).update(
            f"Deleted: {result.get('deleted', 0)} - {space}")
        run_offthread(self, list_snapshots, self._show, self._load_error)
