"""Snapshots screen - Irreversible Action; reports actually-Reclaimed space."""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from cleaner.snapshots import clean_snapshots
from scanner.snapshots import list_snapshots
from ui.screens._util import push_modal, run_gated, skip_resume_rescan
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
        self._busy = False
        self._scanning = False
        self._rescan()

    def _rescan(self) -> None:
        self.snapshots = []
        self.query_one("#snap-list", Static).update("Scanning…")
        run_gated(self, "_scanning", list_snapshots, self._show, self._load_error)

    def on_screen_resume(self) -> None:
        if skip_resume_rescan(self) or self._busy or self._scanning:
            return
        self._rescan()

    def _load_error(self, exc: Exception) -> None:
        self.notify(f"Failed to list snapshots: {exc}", severity="error")

    def _show(self, snaps) -> None:
        self.snapshots = snaps
        listing = "\n".join(s.get("name", "?") for s in snaps) or "No snapshots found."
        self.query_one("#snap-list", Static).update(listing)

    def action_delete_all(self) -> None:
        # _busy spans TypedGateModal -> clean_snapshots worker. Set here,
        # before the gate is pushed, so an escape+re-entry mid-flight (once
        # the gate is answered and the worker is running) can't race a
        # resume-triggered rescan against the delete. run_gated below owns
        # the flag's terminal edge; the declined branch clears it directly.
        if not self.snapshots:
            self.notify("No snapshots to delete.")
            return
        if self._busy:
            self.notify("Already deleting…")
            return
        self._busy = True

        def _resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self._busy = False
                self.notify("Snapshots kept.")
                return
            run_gated(self, "_busy", lambda: clean_snapshots(dry_run=False),
                      self._report, self._delete_error)

        push_modal(
            self,
            TypedGateModal(f"Deleting {len(self.snapshots)} snapshot(s)"),
            _resolved,
        )

    def _delete_error(self, exc: Exception) -> None:
        # _busy is cleared by run_gated right after this returns.
        self.notify(f"Failed to delete snapshots: {exc}", severity="error")

    def _report(self, result: dict) -> None:
        # _busy is cleared by run_gated right after this returns.
        reclaimed = result.get("reclaimed_bytes", 0)
        space = (f"Reclaimed ~{format_size(reclaimed)}" if reclaimed
                 else "Reclaimed: unknown (couldn't isolate the freed space)")
        self.query_one("#snap-log", Static).update(
            f"Deleted: {result.get('deleted', 0)} - {space}")
        if result.get("failed", 0) > 0 and result.get("deleted", 0) == 0:
            self.notify(
                "sudo needs authorization - run 'sudo -v' in a terminal, then retry.",
                severity="warning")
        self._rescan()
