"""Privacy screen - browser/tracking cleaning + gated recents clear."""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from cleaner.privacy import clean_privacy, clear_recently_used
# Filters mirror cleaner/privacy.py::clean_browser_data / clean_tracking_data -
# the preview must show exactly what those cleaners will act on.
from scanner.privacy import scan_browser_data, scan_tracking_data
from ui.screens._util import run_offthread
from ui.widgets.category_header import CategoryHeader
from ui.widgets.gates import TypedGateModal
from ui.widgets.report_view import ReportView, render_paths


class PrivacyScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("d", "dry_run", "Dry Run"),
        ("c", "clean", "Clean"),
        ("r", "clear_recents", "Clear Recents"),
        ("v", "toggle_preview", "View Files"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield CategoryHeader("browser_cache")
            yield CategoryHeader("tracking_data")
            yield CategoryHeader("recents")
            yield Static(id="preview")
            yield ReportView(id="report")
        yield Footer()

    def on_mount(self) -> None:
        self._cleaning = False
        self._preview_shown = False

    def action_toggle_preview(self) -> None:
        preview = self.query_one("#preview", Static)
        if self._preview_shown:
            preview.update("")
            self._preview_shown = False
            return

        def _work():
            # Source of truth: cleaner/privacy.py::clean_browser_data (only
            # "caches" items) and clean_tracking_data (excludes Preferences/ByHost).
            browser_paths = [i["path"] for i in scan_browser_data()
                              if i["type"] == "caches"]
            tracking_paths = [i["path"] for i in scan_tracking_data()
                               if "Preferences/ByHost" not in i["path"]]
            return browser_paths, tracking_paths

        def _done(result) -> None:
            browser_paths, tracking_paths = result
            text = "\n\n".join([
                render_paths("browser_cache", browser_paths),
                render_paths("tracking_data", tracking_paths),
            ])
            preview.update(text)
            self._preview_shown = True

        def _error(e: Exception) -> None:
            self.notify(f"Failed: {e}", severity="error")

        run_offthread(self, _work, _done, _error)

    def action_dry_run(self) -> None:
        self._clean(dry_run=True)

    def action_clean(self) -> None:
        self._clean(dry_run=False)

    def _clean(self, dry_run: bool) -> None:
        if self._cleaning:
            self.notify("Already cleaning…")
            return
        self._cleaning = True

        def _work():
            return list(clean_privacy(dry_run=dry_run).values())

        def _done(reports):
            self.query_one(ReportView).show(reports)
            self._cleaning = False

        def _error(e: Exception) -> None:
            self._cleaning = False
            self.notify(f"Failed: {e}", severity="error")

        run_offthread(self, _work, _done, _error)

    def action_clear_recents(self) -> None:
        def _resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self.notify("Recents kept.")
                return

            def _work():
                return clear_recently_used(dry_run=False)

            def _done(stats: dict) -> None:
                self.notify(f"Cleared {stats['cleared']} recent-items list(s)")

            def _error(exc: Exception) -> None:
                self.notify(f"Failed: {exc}", severity="error")

            run_offthread(self, _work, _done, _error)

        self.app.push_screen(
            TypedGateModal("Clearing the recently-used list"), _resolved)
