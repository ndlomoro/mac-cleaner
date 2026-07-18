"""Uninstall screen - app picker; bundle + leftovers reports."""
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header

from cleaner.app_remnants import uninstall_app
from scanner.app_remnants import get_installed_apps
from ui.screens._util import run_offthread
from ui.widgets.gates import ConfirmModal
from ui.widgets.report_view import ReportView
from utils.helpers import format_size


class UninstallScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="apps", cursor_type="row")
        yield ReportView(id="report")
        yield Footer()

    def on_mount(self) -> None:
        self.apps = []
        table = self.query_one(DataTable)
        table.add_columns("App", "Size")
        run_offthread(self, get_installed_apps, self._fill, self._load_error)

    def _load_error(self, exc: Exception) -> None:
        self.notify(f"Failed to list apps: {exc}", severity="error")

    def _fill(self, apps) -> None:
        self.apps = apps
        table = self.query_one(DataTable)
        for app_info in apps:
            table.add_row(app_info["name"], format_size(app_info["size"]))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        app_info = self.apps[event.cursor_row]
        name = app_info["name"]

        def _resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self.notify("Cancelled - nothing was touched.")
                return

            def _work():
                return uninstall_app(name, dry_run=False)

            def _done(result: dict) -> None:
                self.query_one(ReportView).show([result["app"], result["leftovers"]])

            def _error(exc: Exception) -> None:
                self.notify(str(exc), severity="error")

            run_offthread(self, _work, _done, _error)

        self.app.push_screen(
            ConfirmModal(f"Uninstall {name} (~{format_size(app_info['size'])}) "
                         f"and Trash its leftovers?"),
            _resolved,
        )
