"""Dev Junk - project artifacts: browse, pick individually, confirm.

Structural rules (see CONTEXT.md): nothing pre-selected, no select-all,
user_selected=True is honest because paths come from live checkbox state.
project_artifacts is a user_data category, so hard-protected paths are
still skipped by safe_delete even though the user picked them.

The Docker and Simulators zones are a different shape: docker_junk/
ios_simulators are via_trash=False categories (see registry) - they are
pruned/deleted by their own tools (docker, xcrun), never routed through
safe_delete/Trash, and their "Reclaimed" wording is genuinely earned
(docker/xcrun report the real freed figure themselves).
"""
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Footer, Header, SelectionList, Static
from textual.widgets.selection_list import Selection

from core.deleter import DeleteReport, ReclaimReport, reclaim, safe_delete
from scanner.dev_junk import find_docker_junk, find_project_artifacts, find_simulators
from ui.screens._util import push_modal, run_gated, run_offthread, skip_resume_rescan
from ui.widgets.category_header import CategoryHeader
from ui.widgets.gates import ConfirmModal, TypedGateModal
from ui.widgets.report_view import ReportView
from utils.helpers import format_size, run_command


class DevJunkScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("t", "trash_selected", "Move to Trash"),
        ("D", "docker_prune", "Docker Prune"),
        ("S", "simulators_prune", "Clean Simulators"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield CategoryHeader("project_artifacts")
        yield SelectionList(id="list-artifacts")
        yield Static("Nothing selected.", id="sel-total")
        yield Vertical(id="docker-section")
        yield Vertical(id="sims-section")
        yield ReportView(id="report")
        yield Footer()

    def on_mount(self) -> None:
        self._scanning = False
        self._trashing = False
        self._pruning = False
        self._sim_cleaning = False
        self._docker: dict | None = None
        self._sims: list[dict] = []
        self._rescan()

    def _rescan(self) -> None:
        # option index -> item dict
        self.items: dict[int, dict] = {}
        self.query_one("#list-artifacts", SelectionList).clear_options()
        self.query_one("#sel-total", Static).update("Nothing selected.")
        self.query_one(ReportView).update("")
        self.query_one("#docker-section").remove_children()
        self.query_one("#sims-section").remove_children()
        self.sub_title = "Dev Junk - scanning…"
        self._scanning = True
        self.run_worker(self._scan, thread=True)

    def on_screen_resume(self) -> None:
        if (skip_resume_rescan(self) or self._scanning or self._trashing
                or self._pruning or self._sim_cleaning):
            return
        self._rescan()

    # ---------- scanning ----------

    def _scan(self) -> None:
        # Runs in a thread worker (see on_mount/_rescan) - find_docker_junk and
        # find_simulators shell out to docker/xcrun, so they must never run on
        # the UI thread; sharing this worker with the artifacts scan keeps
        # that guarantee without a second gated round-trip.
        try:
            rows = find_project_artifacts()
            self.app.call_from_thread(self._fill, rows)
            docker = find_docker_junk()
            self.app.call_from_thread(self._fill_docker, docker)
            sims = find_simulators()
            self.app.call_from_thread(self._fill_sims, sims)
            self.app.call_from_thread(self._scan_done)
        except Exception as e:  # noqa: BLE001 - boundary: never let a raise kill the app
            self.app.call_from_thread(self._scan_error, e)

    def _scan_error(self, e: Exception) -> None:
        self._scanning = False
        self.notify(f"Scan failed: {e}", severity="error")

    def _fill(self, rows: list[dict]) -> None:
        sel = self.query_one("#list-artifacts", SelectionList)
        for i, item in enumerate(rows):
            self.items[i] = item
            label = (f"{format_size(item['size']):>10}  {item['age_days']:>4}d idle  "
                      f"{item['kind']:<14} {item['project']}")
            sel.add_option(Selection(label, i, initial_state=False))
        # Options added after mount don't auto-highlight (unlike options passed
        # at construction time); without this, space/enter do nothing until the
        # user first navigates with an arrow key.
        if sel.highlighted is None and sel.option_count > 0:
            sel.highlighted = 0

    def _scan_done(self) -> None:
        self._scanning = False
        self.sub_title = "Dev Junk"

    # ---------- Docker / Simulators zones ----------

    def _fill_docker(self, docker: dict | None) -> None:
        # None (docker absent) -> section stays empty, no CategoryHeader at all.
        # remove_children() schedules an async prune rather than acting
        # in-place, so a remove-then-mount-with-the-same-id in one synchronous
        # call (as happens on a docker-only rescan, where the previous #docker
        # Static is still mounted) raises DuplicateIds. Update the existing
        # Static in place when the section is already showing one instead.
        self._docker = docker
        section = self.query_one("#docker-section")
        if docker is None:
            section.remove_children()
            return
        text = (f"Docker: ~{format_size(docker['images_bytes'])} images / "
                f"~{format_size(docker['volumes_bytes'])} volumes / "
                f"~{format_size(docker['build_cache_bytes'])} build cache reclaimable")
        try:
            section.query_one("#docker", Static).update(text)
        except NoMatches:
            section.remove_children()
            section.mount(CategoryHeader("docker_junk"))
            section.mount(Static(text, id="docker"))

    def _fill_sims(self, sims: list[dict]) -> None:
        # [] (xcrun absent, or nothing unavailable) -> section stays empty.
        # See _fill_docker for why an already-mounted #sims Static is updated
        # in place rather than removed-and-remounted synchronously.
        self._sims = sims
        section = self.query_one("#sims-section")
        if not sims:
            section.remove_children()
            return
        lines = "\n".join(s.get("name", "?") for s in sims)
        try:
            section.query_one("#sims", Static).update(lines)
        except NoMatches:
            section.remove_children()
            section.mount(CategoryHeader("ios_simulators"))
            section.mount(Static(lines, id="sims"))

    def _rescan_docker(self) -> None:
        # Read-only refresh after a prune - reuses _scanning (already covered
        # by on_screen_resume) rather than a dedicated flag, since it's set
        # synchronously here before returning, closing the gap the same way
        # SnapshotsScreen's post-delete _rescan() does.
        self._scanning = True

        def _done(docker: dict | None) -> None:
            self._fill_docker(docker)
            self._scanning = False

        def _error(exc: Exception) -> None:
            self._scanning = False
            self.notify(f"Docker rescan failed: {exc}", severity="error")

        run_offthread(self, find_docker_junk, _done, _error)

    def _rescan_sims(self) -> None:
        self._scanning = True

        def _done(sims: list[dict]) -> None:
            self._fill_sims(sims)
            self._scanning = False

        def _error(exc: Exception) -> None:
            self._scanning = False
            self.notify(f"Simulators rescan failed: {exc}", severity="error")

        run_offthread(self, find_simulators, _done, _error)

    def action_docker_prune(self) -> None:
        if self._docker is None:
            self.notify("Docker is not installed.")
            return
        if self._pruning:
            self.notify("Already pruning…")
            return
        self._pruning = True

        def _gate_resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self._pruning = False
                self.notify("Docker prune cancelled.")
                return

            def _volumes_resolved(prune_volumes: bool | None) -> None:
                argv = ["docker", "system", "prune", "-af"]
                if prune_volumes:
                    argv.append("--volumes")

                def _work() -> tuple[str, str, int]:
                    return run_command(argv)

                def _done(result: tuple[str, str, int]) -> None:
                    stdout, _stderr, _rc = result
                    lines = stdout.strip().splitlines()
                    tail = lines[-1] if lines else "done"
                    self.notify(f"Reclaimed: {tail}")
                    self._rescan_docker()

                def _error(exc: Exception) -> None:
                    self.notify(f"Docker prune failed: {exc}", severity="error")

                run_gated(self, "_pruning", _work, _done, _error)

            push_modal(
                self,
                ConfirmModal("Also prune volumes? Volumes can hold real data "
                              "(databases)."),
                _volumes_resolved,
            )

        push_modal(
            self,
            TypedGateModal("Docker prune (images + build cache) cannot be undone"),
            _gate_resolved,
        )

    def action_simulators_prune(self) -> None:
        if not self._sims:
            self.notify("Xcode simulators not found.")
            return
        if self._sim_cleaning:
            self.notify("Already cleaning…")
            return
        self._sim_cleaning = True

        def _resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self._sim_cleaning = False
                self.notify("Simulator cleanup cancelled.")
                return

            def _work() -> tuple[str, str, int]:
                return run_command(["xcrun", "simctl", "delete", "unavailable"])

            def _done(result: tuple[str, str, int]) -> None:
                self.notify("Deleted unavailable simulators.")
                self._rescan_sims()

            def _error(exc: Exception) -> None:
                self.notify(f"Simulator cleanup failed: {exc}", severity="error")

            run_gated(self, "_sim_cleaning", _work, _done, _error)

        push_modal(
            self,
            TypedGateModal("Deleting unavailable simulators cannot be undone"),
            _resolved,
        )

    # ---------- selected-total footer ----------

    def on_selection_list_selected_changed(
        self, event: SelectionList.SelectedChanged
    ) -> None:
        self._update_selected_total()

    def _update_selected_total(self) -> None:
        sel = self.query_one("#list-artifacts", SelectionList)
        count = 0
        total = 0
        for i in sel.selected:
            item = self.items[i]
            count += 1
            total += item["size"]
        static = self.query_one("#sel-total", Static)
        if count == 0:
            static.update("Nothing selected.")
        else:
            static.update(f"Selected: {count} item(s) (~{format_size(total)})")

    # ---------- trashing ----------

    def action_trash_selected(self) -> None:
        # _trashing spans ConfirmModal -> trash worker -> (if anything was
        # trashed) reclaim gate -> reclaim worker/decline. It's set here,
        # before the ConfirmModal is even pushed, and only cleared in a
        # branch that truly ends the flow: the "nothing selected" early-
        # return below never sets it in the first place; the
        # ConfirmModal-declined branch and the trash worker's error branch
        # clear it directly; the trash-done branch clears it only when no
        # reclaim is offered, otherwise handing the flag off to
        # _offer_reclaim exactly like Junk's chain.
        if self._trashing:
            self.notify("Already trashing…")
            return
        sel = self.query_one("#list-artifacts", SelectionList)
        rows = [self.items[i] for i in sel.selected]
        if not rows:
            self.notify("Nothing selected.")
            return

        count = len(rows)
        total = sum(r["size"] for r in rows)
        self._trashing = True

        def _resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self._trashing = False
                self.notify("Cancelled - nothing was touched.")
                return

            def _work() -> DeleteReport:
                return safe_delete(rows, "project_artifacts",
                                    dry_run=False, user_selected=True)

            def _done(report: DeleteReport) -> None:
                self.query_one(ReportView).show([report])
                self._refresh_list(report)
                if report.trashed:
                    self._offer_reclaim(report)  # _trashing stays True - see _offer_reclaim
                else:
                    self._trashing = False

            def _error(exc: Exception) -> None:
                self._trashing = False
                self.notify(f"Trash failed: {exc}", severity="error")

            run_offthread(self, _work, _done, _error)

        push_modal(
            self,
            ConfirmModal(f"Move {count} item(s) (~{format_size(total)}) to Trash?"),
            _resolved,
        )

    def _refresh_list(self, report: DeleteReport) -> None:
        # Only drop paths safe_delete actually TRASHED - skipped (hard-
        # protected, running app, vanished) and failed items must stay listed
        # and re-selectable, matching what ReportView reports.
        trashed_paths = {r.path for r in report.trashed}
        sel = self.query_one("#list-artifacts", SelectionList)
        keep = {i: it for i, it in self.items.items()
                if it["path"] not in trashed_paths}
        sel.clear_options()
        self.items = {}
        self._fill(list(keep.values()))
        # clear_options()/add_option() don't fire SelectedChanged; the
        # refreshed list starts with nothing selected, so reset explicitly.
        self._update_selected_total()

    # ---------- reclaim (parity with Junk/Space Finder screens) ----------

    def _offer_reclaim(self, report: DeleteReport) -> None:
        # Entered with self._trashing already True (see action_trash_selected).
        # This is the last leg of the trash/reclaim chain: the declined
        # branch clears it manually (no further async step), and the
        # confirmed branch's reclaim worker uses run_gated so the flag
        # clears exactly when the reclaim worker's own done/error
        # terminates - not before.
        total = report.trashed_bytes

        def _resolved(confirmed: bool | None) -> None:
            if confirmed:
                def _work() -> ReclaimReport:
                    return reclaim([report])

                def _done(result: ReclaimReport) -> None:
                    self.notify(f"Reclaimed ~{format_size(result.freed_bytes)} "
                                f"({result.deleted} items)")

                def _error(exc: Exception) -> None:
                    self.notify(f"Reclaim failed: {exc}", severity="error")

                run_gated(self, "_trashing", _work, _done, _error)
            else:
                self._trashing = False
                self.notify("Kept in Trash - recover anytime with Put Back.")

        push_modal(
            self,
            TypedGateModal(f"Permanently delete these items to reclaim "
                           f"~{format_size(total)}"),
            _resolved,
        )
