"""Space Finder - Reclaimable User Data: browse, pick individually, confirm.

Structural rules (see CONTEXT.md): nothing pre-selected, no select-all,
user_selected=True is honest because paths come from live checkbox state,
and the Keep-One Invariant is enforced behind the deletion interface
(core.deleter.trash_selection), not by this screen.
"""
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Footer, Header, SelectionList, Static, TabbedContent, TabPane,
)
from textual.widgets.selection_list import Selection

from core.dedup import find_keep_one_violations
from core.deleter import DeleteReport, ReclaimReport, reclaim, trash_selection
from scanner.duplicates import find_duplicates, pick_keeper
from scanner.large_files import find_large_files
from scanner.system_data import scan_space_finder
from ui.screens._util import push_modal, run_gated, run_offthread, skip_resume_rescan
from ui.widgets.gates import ConfirmModal, TypedGateModal
from ui.widgets.report_view import ReportView
from utils.helpers import format_size

TABS = ("downloads", "ios_backups", "large_files", "duplicates")


def _row_label(category: str, item: dict) -> str:
    """Build a SelectionList option label for one scanned row.

    ios_backups rows carrying a device_name get a device/staleness label;
    everything else (including metadata-less ios_backups rows) keeps the
    generic size/age/path label.
    """
    age = f"{item.get('age_days', 0):>4.0f}"
    if category == "ios_backups" and item.get("device_name") is not None:
        label = (f"{format_size(item['size']):>10}  {age}d since backup  "
                 f"{item['device_name']}")
        if item.get("ios_version") is not None:
            label += f" (iOS {item['ios_version']})"
        # Two devices can share a display name (reset-and-repaired, or two
        # phones the user named the same) - the path tail is what makes
        # otherwise-identical rows distinguishable (dev_junk convention).
        label += f"  [dim]…{item['path'][-40:]}[/dim]"
        return label
    base = f"{format_size(item['size']):>10}  {age}d  …{item['path'][-70:]}"
    if category == "duplicates" and item["path"] == item.get("keeper"):
        return "★ keep  " + base
    return base


class SpaceFinderScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("t", "trash_selected", "Move to Trash"),
        ("k", "select_dupes", "Select duplicates"),
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

    def _busy(self) -> bool:
        """True if a scan or trash pass is in flight - action entry points
        and on_screen_resume must check this before starting/rescanning."""
        return self._scanning or self._trashing

    def on_screen_resume(self) -> None:
        if skip_resume_rescan(self) or self._busy():
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
                keeper = pick_keeper(group["files"])
                for p in group["files"]:
                    dups.append({"path": p, "size": group["size"],
                                 "age_days": 0, "group": group["hash"],
                                 "keeper": keeper})
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
            label = _row_label(category, item)
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

    def _duplicate_groups(self) -> list[frozenset[str]]:
        """Full membership of every known Duplicate Group, from the scan.

        Includes copies the user left unselected - the deletion interface needs
        the whole group to tell whether a batch would remove the last survivor.
        """
        groups: dict[str, set[str]] = {}
        for item in self.items["duplicates"].values():
            groups.setdefault(item["group"], set()).add(item["path"])
        return [frozenset(paths) for paths in groups.values()]

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

    # ---------- keeper selection (k) ----------

    def action_select_dupes(self) -> None:
        """One-keystroke bulk-select: every non-keeper duplicate row, across
        every group, in one press. Keeper rows are never selected here - the
        Keep-One handler above stays the backstop against manual mistakes."""
        if self._busy():
            self.notify("Busy - wait for the current operation.")
            return
        items = self.items["duplicates"]
        if not items:
            self.notify("No duplicates found.")
            return
        sel = self.query_one("#list-duplicates", SelectionList)
        for i, item in items.items():
            if item["path"] != item.get("keeper"):
                sel.select(i)

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

        # Keep-One Invariant: the authority lives behind the deletion interface
        # (trash_selection re-checks and refuses). This is the early, pre-modal
        # warning so the user is never asked to confirm a batch that would be
        # refused - the same check, over the union of picks across every tab,
        # so a group reached wholesale via the Large Files/Downloads tabs is
        # caught just like one selected in the Duplicates tab.
        picked_paths = {row["path"] for rows in picked.values() for row in rows}
        if find_keep_one_violations(picked_paths, self._duplicate_groups()):
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
                # trash_selection owns the Keep-One Invariant and dispatches
                # every category (including large_files) through safe_delete;
                # the pre-modal check above already cleared this batch, so the
                # re-check inside is the authoritative backstop.
                return trash_selection(picked, self._duplicate_groups(),
                                       dry_run=False)

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
        # re-selectable, matching what ReportView reports. Reconcile every
        # tab affected by trashed_paths, not just the ones the user picked
        # from directly - a duplicate's copy can be trashed via a DIFFERENT
        # tab (e.g. the keeper picked from Large Files), which would
        # otherwise leave the Duplicates tab listing a path that no longer
        # exists and stamped with a now-dead "keeper".
        trashed_paths = {r.path for report in reports for r in report.trashed}
        affected = set(picked) | {
            key for key in TABS
            if any(it["path"] in trashed_paths
                   for it in self.items[key].values())
        }
        for key in affected:
            keep = {i: it for i, it in self.items[key].items()
                    if it["path"] not in trashed_paths}
            if key == "duplicates":
                # Restamp keepers for every remaining group - trashing a
                # keeper (from any tab) means one of the survivors must take
                # over the ★, and a group reduced to a single row keeps that
                # row stamped as its own keeper (correctly unselectable by k).
                by_group: dict[str, list[dict]] = {}
                for it in keep.values():
                    by_group.setdefault(it["group"], []).append(it)
                for members in by_group.values():
                    keeper = pick_keeper([m["path"] for m in members])
                    for m in members:
                        m["keeper"] = keeper
            sel = self.query_one(f"#list-{key}", SelectionList)
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
