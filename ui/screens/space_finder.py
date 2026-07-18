"""Space Finder - Reclaimable User Data: browse, pick individually, confirm.

Structural rules (see CONTEXT.md): nothing pre-selected, no select-all,
user_selected=True is honest because paths come from live checkbox state,
and the Duplicates tab enforces the Keep-One Invariant.
"""
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, SelectionList, TabbedContent, TabPane
from textual.widgets.selection_list import Selection

from core.deleter import DeleteReport, ReclaimReport, reclaim, safe_delete
from scanner.duplicates import find_duplicates
from scanner.large_files import find_large_files
from scanner.system_data import scan_space_finder
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
        yield ReportView(id="report")
        yield Footer()

    def on_mount(self) -> None:
        # per-category: option index -> item dict; duplicates items carry "group"
        self.items: dict[str, dict[int, dict]] = {k: {} for k in TABS}
        self.sub_title = "Space Finder - scanning…"
        self.run_worker(self._scan, thread=True)

    # ---------- scanning ----------

    def _scan(self) -> None:
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
        self.sub_title = "Space Finder"

    # ---------- Keep-One Invariant ----------

    def on_selection_list_selected_changed(
        self, event: SelectionList.SelectedChanged
    ) -> None:
        sel = event.selection_list
        if sel.id != "list-duplicates":
            return
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
                sel.deselect(chosen[-1])
                self.notify("One copy of each duplicate is always kept.",
                            severity="warning")

    # ---------- trashing ----------

    def action_trash_selected(self) -> None:
        picked: dict[str, list[dict]] = {}
        for key in TABS:
            sel = self.query_one(f"#list-{key}", SelectionList)
            rows = [self.items[key][i] for i in sel.selected]
            if rows:
                picked[key] = rows
        if not picked:
            self.notify("Nothing selected.")
            return
        count = sum(len(v) for v in picked.values())
        total = sum(f["size"] for v in picked.values() for f in v)

        def _resolved(confirmed: bool | None) -> None:
            if not confirmed:
                self.notify("Cancelled - nothing was touched.")
                return
            reports = [
                safe_delete(rows, category, dry_run=False, user_selected=True)
                for category, rows in picked.items()
            ]
            self.query_one(ReportView).show(reports)
            self._refresh_lists(picked)
            if any(r.trashed for r in reports):
                self._offer_reclaim(reports)

        self.app.push_screen(
            ConfirmModal(f"Move {count} item(s) (~{format_size(total)}) to Trash?"),
            _resolved,
        )

    def _refresh_lists(self, picked: dict[str, list[dict]]) -> None:
        trashed_paths = {f["path"] for v in picked.values() for f in v}
        for key in picked:
            sel = self.query_one(f"#list-{key}", SelectionList)
            keep = {i: it for i, it in self.items[key].items()
                    if it["path"] not in trashed_paths}
            sel.clear_options()
            self.items[key] = {}
            self._fill(key, list(keep.values()))

    # ---------- reclaim (parity with Junk screen) ----------

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
