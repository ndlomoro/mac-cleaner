"""Privacy screen - browser/tracking cleaning + gated recents clear."""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header

from cleaner.privacy import clean_privacy, clear_recently_used
from ui.widgets.category_header import CategoryHeader
from ui.widgets.gates import TypedGateModal
from ui.widgets.report_view import ReportView


class PrivacyScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("d", "dry_run", "Dry Run"),
        ("c", "clean", "Clean"),
        ("r", "clear_recents", "Clear Recents"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield CategoryHeader("browser_cache")
            yield CategoryHeader("tracking_data")
            yield CategoryHeader("recents")
            yield ReportView(id="report")
        yield Footer()

    def on_mount(self) -> None:
        self._cleaning = False

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

        self.run_worker(lambda: self.app.call_from_thread(_done, _work()),
                        thread=True)

    def action_clear_recents(self) -> None:
        def _resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self.notify("Recents kept.")
                return
            stats = clear_recently_used(dry_run=False)
            self.notify(f"Cleared {stats['cleared']} recent-items list(s)")

        self.app.push_screen(
            TypedGateModal("Clearing the recently-used list"), _resolved)
