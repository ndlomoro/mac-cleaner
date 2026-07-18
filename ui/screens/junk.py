"""System Data screen - Junk only; bulk cleaning allowed."""
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from cleaner.system_data import clean_files
from core.deleter import DeleteReport, ReclaimReport, reclaim
from scanner.system_data import scan_all
from ui.widgets.category_header import CategoryHeader
from ui.widgets.gates import TypedGateModal
from ui.widgets.report_view import ReportView
from utils.helpers import format_size


class JunkScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("d", "dry_run", "Dry Run"),
        ("c", "clean", "Clean"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="junk-body")
        yield ReportView(id="report")
        yield Footer()

    def on_mount(self) -> None:
        self.results = {}
        self._cleaning = False
        self.sub_title = "System Data (Junk) - scanning…"
        self.run_worker(self._scan, thread=True)

    def _scan(self) -> None:
        for res in scan_all():
            self.app.call_from_thread(self._add_category, res)
        self.app.call_from_thread(self._scan_done)

    def _add_category(self, res) -> None:
        self.results[res.category] = res
        body = self.query_one("#junk-body")
        body.mount(CategoryHeader(res.category))
        body.mount(Static(f"  {res.name}: {res.file_count} items (~{res.human_size})"))

    def _scan_done(self) -> None:
        self.sub_title = "System Data (Junk)"

    def action_dry_run(self) -> None:
        self._run_clean(dry_run=True)

    def action_clean(self) -> None:
        self._run_clean(dry_run=False)

    def _run_clean(self, dry_run: bool) -> None:
        if self._cleaning:
            self.notify("Already cleaning…")
            return
        self._cleaning = True

        def _work() -> list[DeleteReport]:
            return [clean_files(res, dry_run=dry_run)
                    for res in self.results.values()]

        def _done(reports: list[DeleteReport]) -> None:
            self.query_one(ReportView).show(reports)
            if not dry_run and any(r.trashed for r in reports):
                self._offer_reclaim(reports)
            self._cleaning = False

        self.run_worker(lambda: self.app.call_from_thread(_done, _work()),
                        thread=True)

    def _offer_reclaim(self, reports: list[DeleteReport]) -> None:
        total = sum(r.trashed_bytes for r in reports)

        def _resolved(confirmed: bool | None) -> None:
            if confirmed:
                def _work() -> ReclaimReport:
                    return reclaim(reports)

                def _done(result: ReclaimReport) -> None:
                    self.notify(f"Reclaimed ~{format_size(result.freed_bytes)} "
                                f"({result.deleted} items)")

                self.run_worker(lambda: self.app.call_from_thread(_done, _work()),
                                thread=True)
            else:
                self.notify("Kept in Trash - recover anytime with Put Back.")

        self.app.push_screen(
            TypedGateModal(f"Permanently delete these items to reclaim "
                           f"~{format_size(total)}"),
            _resolved,
        )
