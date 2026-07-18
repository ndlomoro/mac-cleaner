"""System Data screen - Junk only; bulk cleaning allowed."""
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from cleaner.system_data import clean_files
from core.deleter import DeleteReport, ReclaimReport, reclaim
from scanner.system_data import scan_all
from ui.screens._util import push_modal, run_gated, run_offthread, skip_resume_rescan
from ui.widgets.category_header import CategoryHeader
from ui.widgets.gates import TypedGateModal
from ui.widgets.report_view import ReportView, render_paths
from utils.helpers import format_size


class JunkScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("d", "dry_run", "Dry Run"),
        ("c", "clean", "Clean"),
        ("v", "toggle_preview", "View Files"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="junk-body")
        yield Static(id="preview")
        yield ReportView(id="report")
        yield Footer()

    def on_mount(self) -> None:
        self._cleaning = False
        self._scanning = False
        self._rescan()

    def _rescan(self) -> None:
        self.results = {}
        self._preview_shown = False
        self.query_one("#junk-body").remove_children()
        self.query_one("#preview", Static).update("")
        self.query_one(ReportView).update("")
        self.sub_title = "System Data (Junk) - scanning…"
        self._scanning = True
        self.run_worker(self._scan, thread=True)

    def on_screen_resume(self) -> None:
        if skip_resume_rescan(self) or self._cleaning or self._scanning:
            return
        self._rescan()

    def action_toggle_preview(self) -> None:
        preview = self.query_one("#preview", Static)
        if self._preview_shown:
            preview.update("")
            self._preview_shown = False
            return
        parts = [render_paths(res.name, [f["path"] for f in res.files])
                 for res in self.results.values()]
        preview.update("\n\n".join(parts))
        self._preview_shown = True

    def _scan(self) -> None:
        try:
            for res in scan_all():
                self.app.call_from_thread(self._add_category, res)
            self.app.call_from_thread(self._scan_done)
        except Exception as e:  # noqa: BLE001 - boundary: never let a raise kill the app
            self.app.call_from_thread(self._scan_error, e)

    def _add_category(self, res) -> None:
        self.results[res.category] = res
        body = self.query_one("#junk-body")
        body.mount(CategoryHeader(res.category))
        body.mount(Static(f"  {res.name}: {res.file_count} items (~{res.human_size})"))

    def _scan_done(self) -> None:
        self._scanning = False
        self.sub_title = "System Data (Junk)"

    def _scan_error(self, e: Exception) -> None:
        self._scanning = False
        self.notify(f"Scan failed: {e}", severity="error")

    def action_dry_run(self) -> None:
        self._run_clean(dry_run=True)

    def action_clean(self) -> None:
        self._run_clean(dry_run=False)

    def _run_clean(self, dry_run: bool) -> None:
        # _cleaning is set here, at the entry point, and is NOT cleared by a
        # plain run_offthread completion: when a real clean trashes anything,
        # _done chains into the reclaim gate + reclaim worker, and the flag
        # must stay True across that whole chain (see _offer_reclaim) so a
        # resume mid-reclaim doesn't rescan and clobber state. It's cleared
        # right here in _done only on the branch that does NOT chain further
        # (dry-run, or nothing trashed), and in _error (which never chains).
        if self._cleaning:
            self.notify("Already cleaning…")
            return
        self._cleaning = True

        def _work() -> list[DeleteReport]:
            return [clean_files(res, dry_run=dry_run)
                    for res in self.results.values()]

        def _done(reports: list[DeleteReport]) -> None:
            self.query_one(ReportView).show(reports)
            if not dry_run:
                # A real Clean invalidates any preview built from the pre-clean
                # self.results - those paths are now in the Trash, not on disk.
                self.query_one("#preview", Static).update("")
                self._preview_shown = False
            if not dry_run and any(r.trashed for r in reports):
                self._offer_reclaim(reports)  # _cleaning stays True - see _offer_reclaim
            else:
                self._cleaning = False

        def _error(e: Exception) -> None:
            self._cleaning = False
            self.notify(f"Failed: {e}", severity="error")

        run_offthread(self, _work, _done, _error)

    def _offer_reclaim(self, reports: list[DeleteReport]) -> None:
        # Entered with self._cleaning already True (see _run_clean). This is
        # the last leg of the clean/reclaim chain: the declined branch clears
        # it manually (no further async step), and the confirmed branch's
        # reclaim worker uses run_gated so the flag clears exactly when the
        # reclaim worker's own done/error terminates - not before.
        total = sum(r.trashed_bytes for r in reports)

        def _resolved(confirmed: bool | None) -> None:
            if confirmed:
                def _work() -> ReclaimReport:
                    return reclaim(reports)

                def _done(result: ReclaimReport) -> None:
                    self.notify(f"Reclaimed ~{format_size(result.freed_bytes)} "
                                f"({result.deleted} items)")

                def _error(e: Exception) -> None:
                    self.notify(f"Failed: {e}", severity="error")

                run_gated(self, "_cleaning", _work, _done, _error)
            else:
                self._cleaning = False
                self.notify("Kept in Trash - recover anytime with Put Back.")

        push_modal(
            self,
            TypedGateModal(f"Permanently delete these items to reclaim "
                           f"~{format_size(total)}"),
            _resolved,
        )
