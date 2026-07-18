"""Uninstall screen - app picker; dry-run preview, then real uninstall."""
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from cleaner.app_remnants import uninstall_app
from scanner.app_remnants import get_installed_apps
from ui.screens._util import push_modal, run_offthread, skip_resume_rescan
from ui.widgets.gates import ConfirmModal
from ui.widgets.report_view import ReportView, render_paths
from utils.helpers import format_size


class UninstallScreen(Screen):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="apps", cursor_type="row")
        yield Static(id="preview")
        yield ReportView(id="report")
        yield Footer()

    def on_mount(self) -> None:
        self._busy = False
        table = self.query_one(DataTable)
        table.add_columns("App", "Size")
        self._rescan()

    def _rescan(self) -> None:
        self.apps = []
        self.query_one(DataTable).clear()
        self.query_one("#preview", Static).update("")
        self.query_one(ReportView).update("")
        run_offthread(self, get_installed_apps, self._fill, self._load_error)

    def on_screen_resume(self) -> None:
        if skip_resume_rescan(self) or self._busy:
            return
        self._rescan()

    def _load_error(self, exc: Exception) -> None:
        self.notify(f"Failed to list apps: {exc}", severity="error")

    def _fill(self, apps) -> None:
        self.apps = apps
        table = self.query_one(DataTable)
        for app_info in apps:
            table.add_row(app_info["name"], format_size(app_info["size"]))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if self._busy:
            return
        app_info = self.apps[event.cursor_row]
        name = app_info["name"]
        self._busy = True

        def _dry_run_work():
            return uninstall_app(name, dry_run=True)

        def _dry_run_done(dry_result: dict) -> None:
            reports = [dry_result["app"], dry_result["leftovers"]]
            self.query_one(ReportView).show(reports)
            paths = [r.path for report in reports for r in report.trashed]
            self.query_one("#preview", Static).update(
                render_paths("Would move to Trash", paths))
            count = len(paths)
            total = sum(report.trashed_bytes for report in reports)

            def _resolved(confirmed: bool | None) -> None:
                if not confirmed:
                    self._busy = False
                    self.notify("Cancelled - nothing was touched.")
                    return

                def _real_work():
                    return uninstall_app(name, dry_run=False)

                def _real_done(result: dict) -> None:
                    self._busy = False
                    self.query_one(ReportView).show(
                        [result["app"], result["leftovers"]])

                def _real_error(exc: Exception) -> None:
                    self._busy = False
                    self.notify(str(exc), severity="error")

                run_offthread(self, _real_work, _real_done, _real_error)

            push_modal(
                self,
                ConfirmModal(f"Uninstall {name} ({count} item(s), "
                             f"~{format_size(total)}) and Trash its leftovers?"),
                _resolved,
            )

        def _dry_run_error(exc: Exception) -> None:
            self._busy = False
            self.notify(str(exc), severity="error")

        run_offthread(self, _dry_run_work, _dry_run_done, _dry_run_error)
