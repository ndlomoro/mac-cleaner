"""Menu-action handlers. Each takes a `UI` and drives one category end to end.

These are a thin orchestration layer: scan -> render -> gate -> dispatch to
core/cleaner -> report truthfully. All deletion goes through core.deleter, so
the safety guarantees (registry levels, is_protected, Keep-One Invariant) hold
regardless of which UI called them. Gating mirrors the Textual widgets:
recoverable Trashing uses ui.confirm(); Irreversible Actions use ui.typed_gate().
"""
from rich.table import Table

from cleaner.app_remnants import uninstall_app
from cleaner.optimization import optimize_mac
from cleaner.privacy import clean_privacy, clear_recently_used
from cleaner.snapshots import clean_snapshots
from cleaner.system_data import clean_files
from core.dedup import find_keep_one_violations
from core.deleter import DeleteReport, reclaim, safe_delete
from core.deleter import trash_selection
from core.registry import get as get_category
from scanner.app_remnants import find_leftovers, get_installed_apps
from scanner.dev_junk import find_docker_junk, find_project_artifacts, find_simulators
from scanner.duplicates import find_duplicates, pick_keeper
from scanner.large_files import find_large_files
from scanner.optimization import check_launch_agents
from scanner.privacy import scan_browser_data, scan_recently_used, scan_tracking_data
from scanner.snapshots import list_snapshots
from scanner.system_data import scan_all, scan_space_finder
from utils.helpers import format_size, run_command

from cli import render
from cli.io import UI, parse_row_selection

KEEP_ONE_MSG = "One copy of each duplicate is always kept - deselect one copy."


# --------------------------------------------------------------------------
# shared: reclaim offer (the app's only irreversible "empty now" step)
# --------------------------------------------------------------------------

def _offer_reclaim(ui: UI, reports: list[DeleteReport]) -> None:
    """After a real Trash pass, offer to permanently empty exactly what we
    trashed. Declining keeps everything recoverable in the Trash."""
    real = [r for r in reports if not r.dry_run]
    total = sum(r.trashed_bytes for r in real)
    if total <= 0:
        return
    ui.print(f"\n~{format_size(total)} moved to Trash - recoverable until emptied.")
    if ui.typed_gate(f"Permanently delete these items to reclaim ~{format_size(total)}"):
        result = reclaim(real)
        ui.print(f"[green]Reclaimed ~{format_size(result.freed_bytes)} "
                 f"({result.deleted} item(s))[/green]")
        if result.failed:
            ui.print(f"[red]Failed to reclaim {result.failed} item(s).[/red]")
    else:
        ui.print("[dim]Kept in Trash - recover anytime with Put Back.[/dim]")


# --------------------------------------------------------------------------
# 1. Quick Scan (read-only)
# --------------------------------------------------------------------------

def quick_scan(ui: UI) -> None:
    ui.print("Scanning junk categories (read-only)…")
    results = scan_all()
    if not results:
        ui.print("[green]No cleanable junk found.[/green]")
        return
    ui.print(render.scan_table(results))
    ui.print("[dim]Read-only - nothing was touched. Use the category "
             "menus to act.[/dim]")


# --------------------------------------------------------------------------
# 2. System Junk (bulk Trash of SAFE categories, then reclaim)
# --------------------------------------------------------------------------

def system_junk(ui: UI) -> None:
    ui.print("Scanning system junk…")
    results = scan_all()  # non-empty SAFE junk categories, one ScanResult each
    if not results:
        ui.print("[green]No cleanable junk found.[/green]")
        return
    items = {i: r for i, r in enumerate(results, 1)}

    table = Table(title="System Junk", header_style="bold")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Category", style="cyan")
    table.add_column("Items", justify="right")
    table.add_column("Size", justify="right", style="magenta")
    for num in sorted(items):
        r = items[num]
        table.add_row(str(num), r.name, str(r.file_count), r.human_size)
    ui.print(table)

    raw = ui.ask("Categories to Trash (e.g. 3 / 1,2 / a=all / b=back)")
    try:
        parsed = parse_row_selection(raw, len(results))
    except ValueError as e:
        ui.print(f"[yellow]{e}[/yellow]")
        return
    if parsed == "back":
        return
    picked = (list(items.values()) if parsed == "all"
              else [items[i] for i in sorted(parsed)])

    count = sum(r.file_count for r in picked)
    total = sum(r.total_size for r in picked)
    if not ui.confirm(f"Move {count} item(s) (~{format_size(total)}) to Trash?"):
        ui.print("Cancelled - nothing was touched.")
        return
    # Trash exactly the categories the user picked, from this same scan - no
    # re-scan between the preview table and the delete, so what they saw is
    # what gets Trashed.
    reports = [clean_files(r, dry_run=False) for r in picked]
    ui.lines(render.reports_lines(reports))
    _offer_reclaim(ui, reports)


# --------------------------------------------------------------------------
# 3. Space Finder (Reclaimable User Data: browse, pick, Keep-One, reclaim)
# --------------------------------------------------------------------------

_SF_TABS = ("downloads", "ios_backups", "large_files", "duplicates")
_SF_TAB_KEY = {"1": "downloads", "2": "ios_backups",
               "3": "large_files", "4": "duplicates"}


def _space_scan() -> dict[str, dict[int, dict]]:
    """Build 1-based numbered rows per tab, exactly like the Textual screen."""
    items: dict[str, dict[int, dict]] = {k: {} for k in _SF_TABS}
    for res in scan_space_finder():
        if res.category in items:
            for i, f in enumerate(res.files, 1):
                items[res.category][i] = dict(f)
    for i, lf in enumerate(find_large_files(min_size_mb=100, max_results=200), 1):
        items["large_files"][i] = {"path": lf.path, "size": lf.size,
                                   "age_days": lf.age_days}
    n = 1
    for group in find_duplicates():
        keeper = pick_keeper(group["files"])
        for p in group["files"]:
            items["duplicates"][n] = {"path": p, "size": group["size"],
                                      "age_days": 0, "group": group["hash"],
                                      "keeper": keeper}
            n += 1
    return items


def _duplicate_groups(items: dict[str, dict[int, dict]]) -> list[frozenset]:
    groups: dict[str, set[str]] = {}
    for item in items["duplicates"].values():
        groups.setdefault(item["group"], set()).add(item["path"])
    return [frozenset(paths) for paths in groups.values()]


def _sf_overview(ui: UI, items, selected) -> None:
    table = Table(title="Space Finder", header_style="bold")
    table.add_column("#")
    table.add_column("Tab")
    table.add_column("Rows", justify="right")
    table.add_column("Selected", justify="right")
    for num, key in _SF_TAB_KEY.items():
        table.add_row(num, key.replace("_", " ").title(),
                      str(len(items[key])), str(len(selected[key])))
    ui.print(table)
    count = sum(len(s) for s in selected.values())
    total = sum(items[k][i]["size"] for k in _SF_TABS for i in selected[k])
    if count:
        ui.print(f"Selected: {count} item(s) (~{format_size(total)})")
    else:
        ui.print("Nothing selected.")


def _sf_view_tab(ui: UI, key: str, items, selected) -> None:
    if not items[key]:
        ui.print(f"[dim]No {key.replace('_', ' ')} found.[/dim]")
        return
    ui.print(render.rows_table(key.replace("_", " ").title(), items[key],
                               selected[key], keeper_aware=(key == "duplicates")))
    raw = ui.ask("Row numbers to select (replaces this tab's selection; "
                 "a=all, b=back)")
    try:
        parsed = parse_row_selection(raw, len(items[key]))
    except ValueError as e:
        ui.print(f"[yellow]{e} - selection unchanged.[/yellow]")
        return
    if parsed == "back":
        return
    if parsed == "all":
        selected[key] = set(items[key])
    else:
        selected[key] = parsed


def _sf_refresh_after_trash(items, reports: list[DeleteReport]) -> None:
    """Drop only paths that were actually trashed; renumber each affected tab
    and restamp duplicate keepers so a group that lost its keeper survives."""
    trashed = {r.path for report in reports for r in report.trashed}
    for key in _SF_TABS:
        kept = [it for it in items[key].values() if it["path"] not in trashed]
        if key == "duplicates":
            by_group: dict[str, list[dict]] = {}
            for it in kept:
                by_group.setdefault(it["group"], []).append(it)
            for members in by_group.values():
                keeper = pick_keeper([m["path"] for m in members])
                for m in members:
                    m["keeper"] = keeper
        items[key] = {i: it for i, it in enumerate(kept, 1)}


def space_finder(ui: UI) -> None:
    ui.print("Scanning downloads, iOS backups, large files, duplicates…")
    items = _space_scan()
    selected: dict[str, set[int]] = {k: set() for k in _SF_TABS}
    if not any(items.values()):
        ui.print("[green]Nothing to reclaim - no user data found.[/green]")
        return
    ui.print(render.category_header(get_category("large_files")))

    while True:
        _sf_overview(ui, items, selected)
        choice = ui.choose("Pick a tab [1-4] · k=select non-keeper dupes · "
                           "t=Trash selection · b=Back",
                           ["1", "2", "3", "4", "k", "t", "b"])
        if choice == "b":
            return
        if choice in _SF_TAB_KEY:
            _sf_view_tab(ui, _SF_TAB_KEY[choice], items, selected)
            continue
        if choice == "k":
            selected["duplicates"] = {
                i for i, it in items["duplicates"].items()
                if it["path"] != it.get("keeper")
            }
            ui.print(f"Selected {len(selected['duplicates'])} non-keeper "
                     "duplicate(s).")
            continue
        # choice == "t"
        submission = {k: [items[k][i] for i in selected[k]]
                      for k in _SF_TABS if selected[k]}
        if not submission:
            ui.print("Nothing selected.")
            continue
        picked_paths = {row["path"] for rows in submission.values()
                        for row in rows}
        if find_keep_one_violations(picked_paths, _duplicate_groups(items)):
            ui.print(f"[yellow]{KEEP_ONE_MSG}[/yellow]")
            continue
        count = sum(len(v) for v in submission.values())
        total = sum(r["size"] for v in submission.values() for r in v)
        if not ui.confirm(f"Move {count} item(s) (~{format_size(total)}) to Trash?"):
            ui.print("Cancelled - nothing was touched.")
            continue
        reports = trash_selection(submission, _duplicate_groups(items),
                                  dry_run=False)
        ui.lines(render.reports_lines(reports))
        _sf_refresh_after_trash(items, reports)
        selected = {k: set() for k in _SF_TABS}
        _offer_reclaim(ui, reports)


# --------------------------------------------------------------------------
# 4. Privacy (trashable caches + irreversible recents clear)
# --------------------------------------------------------------------------

def privacy(ui: UI) -> None:
    browser = scan_browser_data()
    tracking = scan_tracking_data()
    recents = scan_recently_used()
    table = Table(title="Privacy data", header_style="bold")
    table.add_column("Source", style="cyan")
    table.add_column("Type")
    table.add_column("Size", justify="right", style="magenta")
    for it in browser:
        table.add_row(it["browser"], it["type"], format_size(it["size"]))
    for it in tracking:
        table.add_row("System", it["type"], format_size(it["size"]))
    for it in recents:
        table.add_row("System", it["type"], format_size(it["size"]))
    ui.print(table)
    ui.print("[dim]Browser history is shown for awareness only - this tool "
             "never deletes it.[/dim]")

    choice = ui.choose("1=Trash browser & tracking caches · "
                       "2=Clear recent-items list (irreversible) · b=Back",
                       ["1", "2", "b"])
    if choice == "b":
        return
    if choice == "1":
        preview = list(clean_privacy(dry_run=True).values())
        count = sum(len(r.trashed) for r in preview)
        total = sum(r.trashed_bytes for r in preview)
        if count == 0:
            ui.print("[green]No browser/tracking caches to Trash.[/green]")
            return
        ui.lines(render.reports_lines(preview))
        if not ui.confirm(f"Move {count} item(s) (~{format_size(total)}) to Trash?"):
            ui.print("Cancelled - nothing was touched.")
            return
        real = list(clean_privacy(dry_run=False).values())
        ui.lines(render.reports_lines(real))
        _offer_reclaim(ui, real)
        return
    # choice == "2": recents is an Irreversible Action (in-place rewrite)
    ui.print(render.category_header(get_category("recents")))
    if not ui.typed_gate("Clearing the recent-items list rewrites it in place"):
        ui.print("Left unchanged.")
        return
    stats = clear_recently_used(dry_run=False)
    ui.print(f"Cleared {stats['cleared']} list(s); {stats['failed']} failed.")


# --------------------------------------------------------------------------
# 5. Optimize (developer caches; brew/npm via their own tools)
# --------------------------------------------------------------------------

def optimize(ui: UI) -> None:
    agents = check_launch_agents()
    if agents:
        ui.print(f"{len(agents)} program(s) set to run at login "
                 "(shown for visibility; remove in System Settings):")
        for a in agents[:20]:
            ui.print(f"  {a['name']} [dim]({a['location']})[/dim]")
    if not ui.confirm("Clean developer caches (brew, npm, Xcode DerivedData, "
                      "CocoaPods, pip)?"):
        ui.print("Cancelled - nothing was touched.")
        return
    result = optimize_mac(dry_run=False)
    trash_reports = [v for v in result.values() if isinstance(v, DeleteReport)]
    ui.lines(render.reports_lines(trash_reports))
    for key in ("brew_cleanup", "npm_cache"):
        info = result.get(key, {})
        if isinstance(info, dict) and info.get("message"):
            ui.print(f"[{key}] {info['message']}")
    for key in ("xcode_derived_data", "cocoapods_cache", "pip_cache"):
        info = result.get(key)
        if isinstance(info, dict) and info.get("message"):
            ui.print(f"[{key}] {info['message']}")
    _offer_reclaim(ui, trash_reports)


# --------------------------------------------------------------------------
# 6. Snapshots (Irreversible: tmutil deletes local Time Machine snapshots)
# --------------------------------------------------------------------------

def snapshots(ui: UI) -> None:
    snaps = list_snapshots()
    if not snaps:
        ui.print("[green]No local snapshots found.[/green]")
        return
    ui.print(f"{len(snaps)} local Time Machine snapshot(s):")
    for s in snaps[:40]:
        ui.print(f"  {s['name']}")
    ui.print(render.category_header(get_category("snapshots")))
    if not ui.typed_gate(f"Delete all {len(snaps)} local snapshot(s)"):
        ui.print("Left unchanged.")
        return
    result = clean_snapshots(dry_run=False)
    ui.print(f"Deleted {result.get('deleted', 0)} snapshot(s); "
             f"{result.get('failed', 0)} failed.")


# --------------------------------------------------------------------------
# 7. Uninstall App (app bundle + leftovers -> Trash, then reclaim)
# --------------------------------------------------------------------------

def uninstall(ui: UI) -> None:
    apps = get_installed_apps()
    if not apps:
        ui.print("No applications found in /Applications.")
        return
    items = {i: a for i, a in enumerate(apps, 1)}
    table = Table(title="Installed apps (largest first)", header_style="bold")
    table.add_column("#", justify="right", style="dim")
    table.add_column("App", style="cyan")
    table.add_column("Size", justify="right", style="magenta")
    for num in sorted(items):
        table.add_row(str(num), items[num]["name"],
                      format_size(items[num]["size"]))
    ui.print(table)
    raw = ui.ask("App number to uninstall (b to go back)")
    try:
        parsed = parse_row_selection(raw, len(apps))
    except ValueError as e:
        ui.print(f"[yellow]{e}[/yellow]")
        return
    if parsed == "back":
        return
    if parsed == "all" or len(parsed) != 1:
        ui.print("Uninstall one app at a time - pick a single number.")
        return
    app = items[next(iter(parsed))]
    name = app["name"]

    preview = uninstall_app(name, dry_run=True)
    reports = [preview["app"], preview["leftovers"]]
    count = sum(len(r.trashed) for r in reports)
    total = sum(r.trashed_bytes for r in reports)
    ui.print(f"Uninstalling [cyan]{name}[/cyan] will Trash the app bundle and "
             f"{len(preview['leftovers'].trashed)} leftover item(s):")
    ui.lines(render.reports_lines(reports))
    if not ui.confirm(f"Move {count} item(s) (~{format_size(total)}) to Trash?"):
        ui.print("Cancelled - nothing was touched.")
        return
    real = uninstall_app(name, dry_run=False)
    real_reports = [real["app"], real["leftovers"]]
    ui.lines(render.reports_lines(real_reports))
    _offer_reclaim(ui, real_reports)


# --------------------------------------------------------------------------
# 8. Dev Junk (project artifacts -> Trash; docker/simulators via own tools)
# --------------------------------------------------------------------------

def dev_junk(ui: UI) -> None:
    artifacts = find_project_artifacts()
    items = {i: a for i, a in enumerate(artifacts, 1)}
    selected: set[int] = set()
    docker = find_docker_junk()
    sims = find_simulators()

    while True:
        if items:
            ui.print(render.rows_table("Project artifacts", items, selected))
            total = sum(items[i]["size"] for i in selected)
            ui.print(f"Selected: {len(selected)} item(s) (~{format_size(total)})"
                     if selected else "Nothing selected.")
        else:
            ui.print("[dim]No project artifacts found.[/dim]")
        if docker:
            ui.print(f"Docker: ~{format_size(docker['images_bytes'])} images / "
                     f"~{format_size(docker['volumes_bytes'])} volumes / "
                     f"~{format_size(docker['build_cache_bytes'])} build cache "
                     "reclaimable")
        if sims:
            ui.print(f"{len(sims)} unavailable iOS simulator(s).")

        opts = ["s", "t", "b"] + (["D"] if docker else []) + (["S"] if sims else [])
        choice = ui.choose(
            "s=Select artifacts · t=Trash selected · "
            + ("D=Docker prune · " if docker else "")
            + ("S=Clean simulators · " if sims else "")
            + "b=Back", opts)

        if choice == "b":
            return
        if choice == "s":
            if not items:
                ui.print("Nothing to select.")
                continue
            raw = ui.ask("Row numbers to select (replaces selection; a=all, b=back)")
            try:
                parsed = parse_row_selection(raw, len(items))
            except ValueError as e:
                ui.print(f"[yellow]{e} - selection unchanged.[/yellow]")
                continue
            if parsed == "back":
                continue
            selected = set(items) if parsed == "all" else parsed
            continue
        if choice == "t":
            rows = [items[i] for i in selected]
            if not rows:
                ui.print("Nothing selected.")
                continue
            count = len(rows)
            total = sum(r["size"] for r in rows)
            if not ui.confirm(f"Move {count} item(s) (~{format_size(total)}) "
                              "to Trash?"):
                ui.print("Cancelled - nothing was touched.")
                continue
            report = safe_delete(rows, "project_artifacts", dry_run=False,
                                 user_selected=True)
            ui.lines(render.reports_lines([report]))
            trashed = {r.path for r in report.trashed}
            kept = [it for it in items.values() if it["path"] not in trashed]
            items = {i: it for i, it in enumerate(kept, 1)}
            selected = set()
            _offer_reclaim(ui, [report])
            continue
        if choice == "D":
            _docker_prune(ui)
            docker = find_docker_junk()
            continue
        if choice == "S":
            _simulators_prune(ui)
            sims = find_simulators()
            continue


def _docker_prune(ui: UI) -> None:
    ui.print(render.category_header(get_category("docker_junk")))
    if not ui.typed_gate("Docker prune (images + build cache) cannot be undone"):
        ui.print("Docker prune cancelled.")
        return
    argv = ["docker", "system", "prune", "-af"]
    if ui.confirm("Also prune volumes? Volumes can hold real data (databases)."):
        argv.append("--volumes")
    stdout, stderr, rc = run_command(argv)
    if rc != 0:
        ui.print(f"[red]Docker prune failed: {stderr.strip() or 'unknown error'}[/red]")
        return
    tail = stdout.strip().splitlines()[-1] if stdout.strip() else "done"
    ui.print(f"Reclaimed: {tail}")


def _simulators_prune(ui: UI) -> None:
    ui.print(render.category_header(get_category("ios_simulators")))
    if not ui.typed_gate("Deleting unavailable simulators cannot be undone"):
        ui.print("Simulator cleanup cancelled.")
        return
    stdout, stderr, rc = run_command(["xcrun", "simctl", "delete", "unavailable"])
    if rc != 0:
        ui.print(f"[red]Simulator cleanup failed: "
                 f"{stderr.strip() or 'unknown error'}[/red]")
        return
    ui.print("Deleted unavailable simulators.")
