"""Space Finder - Reclaimable User Data: browse, pick individually, confirm.

Structural rules (see CONTEXT.md): nothing pre-selected, no select-all,
user_selected=True is honest because paths come from live checkbox state,
and the Duplicates tab enforces the Keep-One Invariant.
"""
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Footer, Header, SelectionList, Static, TabbedContent, TabPane,
)
from textual.widgets.selection_list import Selection

from cleaner.large_files import clean_large_files
from core.deleter import DeleteReport, ReclaimReport, reclaim, safe_delete
from scanner.duplicates import find_duplicates
from scanner.large_files import find_large_files
from scanner.system_data import scan_space_finder
from ui.screens._util import push_modal, run_gated, run_offthread, skip_resume_rescan
from ui.widgets.gates import ConfirmModal, TypedGateModal
from ui.widgets.report_view import ReportView
from utils.helpers import format_size

TABS = ("downloads", "ios_backups", "large_files", "duplicates")


class SpaceFinderScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("t", "trash_selected", "Move to Trash"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            for key in TABS:
                with TabPane(key.replace("_", " ").title(), id=f"tab-{key}"):
                    yield SelectionList(id=f"list-{key}")
        yield Static("Nothing selected.", id="sel-total")
        yield ReportView(id="report")
        yield Footer()

    def on_mount(self) -> None:
        self._scanning = False
        self._trashing = False
        self._rescan()

    def _rescan(self) -> None:
        # per-category: option index -> item dict; duplicates items carry "group"
        self.items: dict[str, dict[int, dict]] = {k: {} for k in TABS}
        for key in TABS:
            self.query_one(f"#list-{key}", SelectionList).clear_options()
        self.query_one("#sel-total", Static).update("Nothing selected.")
        self.query_one(ReportView).update("")
        self.sub_title = "Space Finder - scanning…"
        self._scanning = True
        self.run_worker(self._scan, thread=True)

    def on_screen_resume(self) -> None:
        if skip_resume_rescan(self) or self._scanning or self._trashing:
            return
        self._rescan()

    # ---------- scanning ----------

    def _scan(self) -> None:
        try:
            for res in scan_space_finder():
                rows = [dict(f) for f in res.files]
                self.app.call_from_thread(self._fill, res.category, rows)
            large = [{"path": lf.path, "size": lf.size, "age_days": lf.age_days}
                     for lf in find_large_files(min_size_mb=100, max_results=200)]
            self.app.call_from_thread(self._fill, "large_files", large)
            dups = []
            for group in find_duplicates():
                for p in group["files"]:
                    dups.append({"path": p, "size": group["size"],
                                 "age_days": 0, "group": group["hash"]})
            self.app.call_from_thread(self._fill, "duplicates", dups)
            self.app.call_from_thread(self._scan_done)
        except Exception as e:  # noqa: BLE001 - boundary: never let a raise kill the app
            self.app.call_from_thread(self._scan_error, e)

    def _scan_error(self, e: Exception) -> None:
        self._scanning = False
        self.notify(f"Scan failed: {e}", severity="error")

    def _fill(self, category: str, rows: list[dict]) -> None:
        sel = self.query_one(f"#list-{category}", SelectionList)
        for i, item in enumerate(rows):
            self.items[category][i] = item
            age = f"{item.get('age_days', 0):>4.0f}d"
            label = f"{format_size(item['size']):>10}  {age}  …{item['path'][-70:]}"
            sel.add_option(Selection(label, i, initial_state=False))
        # Options added after mount don't auto-highlight (unlike options passed
        # at construction time); without this, space/enter do nothing until the
        # user first navigates with an arrow key.
        if sel.highlighted is None and sel.option_count > 0:
            sel.highlighted = 0

    def _scan_done(self) -> None:
        self._scanning = False
        self.sub_title = "Space Finder"

    # ---------- Keep-One Invariant / footer total ----------

    def on_selection_list_selected_changed(
        self, event: SelectionList.SelectedChanged
    ) -> None:
        sel = event.selection_list
        if sel.id == "list-duplicates":
            items = self.items["duplicates"]
            selected = set(sel.selected)
            by_group: dict[str, list[int]] = {}
            for i in selected:
                by_group.setdefault(items[i]["group"], []).append(i)
            for group_hash, chosen in by_group.items():
                group_size = sum(1 for it in items.values()
                                if it["group"] == group_hash)
                if len(chosen) >= group_size:
                    # refuse: deselect the highest-indexed pick and warn
                    sel.deselect(sorted(chosen)[-1])
                    self.notify("One copy of each duplicate is always kept.",
                                severity="warning")
        self._update_selected_total()

    def _update_selected_total(self) -> None:
        """Recompute the selected-count/size footer across ALL tabs."""
        count = 0
        total = 0
        for key in TABS:
            sel = self.query_one(f"#list-{key}", SelectionList)
            for i in sel.selected:
                item = self.items[key][i]
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
        # branch that truly ends the flow: the "nothing selected"/refused
        # early-returns below never set it in the first place; the
        # ConfirmModal-declined branch and the trash worker's error branch
        # clear it directly; the trash-done branch clears it only when no
        # reclaim is offered, otherwise handing the flag off to
        # _offer_reclaim exactly like Junk's chain.
        if self._trashing:
            self.notify("Already trashing…")
            return
        picked: dict[str, list[dict]] = {}
        for key in TABS:
            sel = self.query_one(f"#list-{key}", SelectionList)
            rows = [self.items[key][i] for i in sel.selected]
            if rows:
                picked[key] = rows
        if not picked:
            self.notify("Nothing selected.")
            return

        # Cross-tab Keep-One enforcement: a duplicate group can also be picked
        # wholesale via the Large Files/Downloads tabs, bypassing the
        # Duplicates-tab guard in on_selection_list_selected_changed. Check
        # every known duplicate group (not just the duplicates tab's own
        # selection) against the full set of picked paths across all tabs.
        picked_paths = {row["path"] for rows in picked.values() for row in rows}
        groups: dict[str, set[str]] = {}
        for item in self.items["duplicates"].values():
            groups.setdefault(item["group"], set()).add(item["path"])
        for group_paths in groups.values():
            if group_paths and group_paths <= picked_paths:
                self.notify(
                    "One copy of each duplicate is always kept - deselect one copy.",
                    severity="warning")
                return

        count = sum(len(v) for v in picked.values())
        total = sum(f["size"] for v in picked.values() for f in v)
        self._trashing = True

        def _resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self._trashing = False
                self.notify("Cancelled - nothing was touched.")
                return

            def _work() -> list[DeleteReport]:
                reports = []
                for category, rows in picked.items():
                    if category == "large_files":
                        reports.append(clean_large_files(
                            [r["path"] for r in rows], dry_run=False))
                    else:
                        reports.append(safe_delete(
                            rows, category, dry_run=False, user_selected=True))
                return reports

            def _done(reports: list[DeleteReport]) -> None:
                self.query_one(ReportView).show(reports)
                self._refresh_lists(picked, reports)
                if any(r.trashed for r in reports):
                    self._offer_reclaim(reports)  # _trashing stays True - see _offer_reclaim
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

    def _refresh_lists(self, picked: dict[str, list[dict]],
                       reports: list[DeleteReport]) -> None:
        # Only drop paths safe_delete actually TRASHED - skipped (hard-protected,
        # running app, vanished) and failed items must stay listed and
        # re-selectable, matching what ReportView reports.
        trashed_paths = {r.path for report in reports for r in report.trashed}
        for key in picked:
            sel = self.query_one(f"#list-{key}", SelectionList)
            keep = {i: it for i, it in self.items[key].items()
                    if it["path"] not in trashed_paths}
            sel.clear_options()
            self.items[key] = {}
            self._fill(key, list(keep.values()))
        # clear_options()/add_option() don't fire SelectedChanged; the
        # refreshed lists start with nothing selected, so reset explicitly.
        self._update_selected_total()

    # ---------- reclaim (parity with Junk screen) ----------

    def _offer_reclaim(self, reports: list[DeleteReport]) -> None:
        # Entered with self._trashing already True (see action_trash_selected).
        # This is the last leg of the trash/reclaim chain: the declined
        # branch clears it manually (no further async step), and the
        # confirmed branch's reclaim worker uses run_gated so the flag
        # clears exactly when the reclaim worker's own done/error
        # terminates - not before.
        total = sum(r.trashed_bytes for r in reports)

        def _resolved(confirmed: bool | None) -> None:
            if confirmed:
                def _work() -> ReclaimReport:
                    return reclaim(reports)

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
