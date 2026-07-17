"""TUI Dashboard - Rich-based interactive interface."""
import sys
from pathlib import Path

# Add project root to path (needed for bundled .app)
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.text import Text
from rich.columns import Columns
from rich import box

from utils.helpers import format_size, get_disk_usage
from scanner.system_data import scan_all
from scanner.large_files import find_large_files
from scanner.duplicates import find_duplicates
from scanner.snapshots import list_snapshots
from scanner.privacy import scan_browser_data, scan_tracking_data
from scanner.app_remnants import get_installed_apps
from scanner.optimization import check_launch_agents
from cleaner.optimization import optimize_mac
from cleaner.system_data import clean_system_data
from cleaner.snapshots import clean_snapshots
from cleaner.privacy import clean_privacy, clear_recently_used

console = Console()

from core import registry
from core.deleter import DeleteReport, reclaim
from scanner.system_data import scan_space_finder

LEVEL_STYLES = {"SAFE": "green", "CAUTION": "yellow", "RISKY": "red"}


def print_category_header(key: str):
    """Level + plain-English explanation, shown before a category's items."""
    cat = registry.get(key)
    style = LEVEL_STYLES[cat.level.value]
    label = f"[{style}]\\[{cat.level.value}][/{style}]"
    suffix = " [dim](cleared directly - not recoverable via Trash)[/dim]" if not cat.via_trash else ""
    console.print(f"{label} {cat.explanation}{suffix}")


def show_delete_report(report: DeleteReport):
    """Truthful summary: Trashed (not 'freed'), skips with reasons, failures."""
    verb = "Would move to Trash" if report.dry_run else "Moved to Trash"
    console.print(f"  [green]{verb}:[/green] {len(report.trashed)} items "
                  f"(~{format_size(report.trashed_bytes)})")
    for r in report.skipped:
        console.print(f"  [yellow]Skipped:[/yellow] {r.path[-60:]} - {r.reason}")
    for r in report.failed:
        console.print(f"  [red]Failed:[/red] {r.path[-60:]} - {r.reason}")


def confirm_irreversible(what: str) -> bool:
    """Typed gate for Irreversible Actions. Returns True only on literal 'yes'."""
    console.print(f"\n[bold red]{what} cannot be undone.[/bold red]")
    answer = Prompt.ask("Type 'yes' to proceed", default="no")
    return answer.strip().lower() == "yes"


def offer_reclaim(reports: list[DeleteReport]):
    """After a real clean: offer surgical empty of exactly what we trashed."""
    real = [r for r in reports if not r.dry_run]
    total = sum(r.trashed_bytes for r in real)
    if not total:
        return
    console.print(f"\n[bold]~{format_size(total)} moved to Trash[/bold] "
                  f"- recoverable until emptied.")
    if confirm_irreversible(f"Permanently deleting these items to reclaim ~{format_size(total)}"):
        result = reclaim(real)
        console.print(f"[green]Reclaimed ~{format_size(result.freed_bytes)} "
                      f"({result.deleted} items)[/green]")
        if result.failed:
            console.print(f"[red]Failed to reclaim {result.failed} items[/red]")
    else:
        console.print("[dim]Kept in Trash - recover anytime with Put Back.[/dim]")


def print_header():
    """Print the app header."""
    header = Text("\n", style="bold")
    header += Text("Mac Cleaner", style="bold cyan")
    header += Text(" v1.0", style="dim white")
    console.print(Panel(header, style="bold cyan", border_style="cyan"))


def show_disk_overview():
    """Show disk usage overview."""
    usage = get_disk_usage()
    if not usage:
        console.print("[yellow]Could not read disk info[/yellow]")
        return

    table = Table(title="Disk Overview", box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Total", format_size(usage["total"]))
    table.add_row("Used", format_size(usage["used"]))
    table.add_row("Free", format_size(usage["free"]))
    table.add_row("Usage", f"[{'green' if usage['percent'] < 70 else 'red'}]{usage['percent']}%[/{'green' if usage['percent'] < 70 else 'red'}]")

    console.print(table)


def show_scan_results(results: list):
    """Display scan results in a table."""
    if not results:
        console.print("[green]No cleanable items found[/green]")
        return

    table = Table(title="Scan Results", box=box.ROUNDED)
    table.add_column("Category", style="cyan")
    table.add_column("Items", justify="right", style="white")
    table.add_column("Size", justify="right", style="magenta")

    for r in results:
        table.add_row(r.name, str(r.file_count), r.human_size)

    total_size = sum(r.total_size for r in results)
    total_files = sum(r.file_count for r in results)
    table.add_row("[bold]TOTAL[/bold]", f"[bold]{total_files}[/bold]", f"[bold]{format_size(total_size)}[/bold]")

    console.print(table)


def show_snapshots(snapshots: list):
    """Display local snapshots."""
    if not snapshots:
        console.print("[green]No local snapshots found[/green]")
        return

    table = Table(title=f"Local Snapshots ({len(snapshots)})", box=box.ROUNDED)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Snapshot", style="cyan")

    for i, snap in enumerate(snapshots, 1):
        table.add_row(str(i), snap["name"][:80] + "...")

    console.print(table)


def show_large_files(files: list):
    """Display large files."""
    if not files:
        console.print("[green]No large files found[/green]")
        return

    table = Table(title=f"Large Files (top {len(files)})", box=box.ROUNDED)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Size", justify="right", style="magenta")
    table.add_column("Age", justify="right", style="yellow")
    table.add_column("Path", style="cyan")

    for i, f in enumerate(files[:20], 1):
        table.add_row(
            str(i),
            f.human_size,
            f"{f.age_days:.0f}d",
            f.path[-60:] if len(f.path) > 60 else f.path,
        )

    console.print(table)


def show_duplicates(groups: list):
    """Display duplicate file groups."""
    if not groups:
        console.print("[green]No duplicate files found[/green]")
        return

    total_wasted = sum(g["wasted"] for g in groups)
    console.print(f"\n[yellow]Found {len(groups)} duplicate groups | Wasted: {format_size(total_wasted)}[/yellow]")

    for i, group in enumerate(groups[:10], 1):
        console.print(f"\n  [bold cyan]Group {i}[/bold cyan] - {format_size(group['size'])} x{len(group['files'])}")
        for f in group["files"][:3]:
            console.print(f"    {f[-60:]}" if len(f) > 60 else f"    {f}")
        if len(group["files"]) > 3:
            console.print(f"    ... and {len(group['files']) - 3} more", style="dim")


def show_privacy_data(browser_data: list, tracking_data: list):
    """Display privacy scan results."""
    table = Table(title="Privacy Data", box=box.ROUNDED)
    table.add_column("Browser/Type", style="cyan")
    table.add_column("Data Type", style="white")
    table.add_column("Size", justify="right", style="magenta")

    for item in browser_data:
        table.add_row(item["browser"], item["type"], format_size(item["size"]))
    for item in tracking_data:
        table.add_row("System", item["type"], format_size(item["size"]))

    console.print(table)


def show_apps(apps: list):
    """Display installed apps."""
    table = Table(title=f"Installed Apps ({len(apps)})", box=box.ROUNDED)
    table.add_column("#", justify="right", style="dim")
    table.add_column("App", style="cyan")
    table.add_column("Size", justify="right", style="magenta")

    for i, app in enumerate(apps[:30], 1):
        table.add_row(str(i), app["name"], format_size(app["size"]))

    console.print(table)


def show_launch_agents(agents: list):
    """Display launch agents."""
    if not agents:
        console.print("[green]No launch agents found[/green]")
        return

    table = Table(title=f"Launch Agents ({len(agents)})", box=box.ROUNDED)
    table.add_column("#", justify="right", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Location", style="white")

    for i, agent in enumerate(agents, 1):
        table.add_row(str(i), agent["name"], agent["location"])

    console.print(table)


def show_main_menu() -> str:
    """Show main menu and return user choice."""
    console.print("\n[bold]Main Menu[/bold]")
    console.print("  [1] Scan System Data     [Scan caches, logs, temp files]")
    console.print("  [2] Find Large Files     [Find files > 100MB]")
    console.print("  [3] Find Duplicates      [Find duplicate files]")
    console.print("  [4] Local Snapshots      [View/delete Time Machine snapshots]")
    console.print("  [5] Privacy Cleaner      [Browser cache, tracking data]")
    console.print("  [6] App Uninstaller      [Remove apps + leftovers]")
    console.print("  [7] Optimization         [Brew cleanup, dev caches]")
    console.print("  [8] Full Scan            [Run all scans]")
    console.print("  [9] Space Finder         [Old downloads, iOS backups - pick individually]")
    console.print("  [q] Quit")

    return Prompt.ask("\n  Choose", default="1")


def view_system_data_files(results: list):
    """List files in system data scan results."""
    for r in results:
        console.print(f"\n[bold cyan]{r.name}[/bold cyan] ({r.file_count} items, {r.human_size})")
        table = Table(box=box.MINIMAL_DOUBLE_HEAD)
        table.add_column("Path", style="white")
        table.add_column("Size", justify="right", style="magenta")
        # Show up to 30 files per category
        for f in r.files[:30]:
            path = f["path"]
            if len(path) > 90:
                path = "..." + path[-87:]
            table.add_row(path, format_size(f["size"]))
        console.print(table)
        if len(r.files) > 30:
            console.print(f"  ... and {len(r.files) - 30} more items", style="dim")


def view_privacy_files(browser_data: list, tracking_data: list):
    """List privacy database and cache paths."""
    console.print("\n[bold cyan]Privacy files/folders to be cleared:[/bold cyan]")
    table = Table(box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Type/Browser", style="cyan")
    table.add_column("Path", style="white")
    table.add_column("Size", justify="right", style="magenta")

    for item in browser_data:
        path = item["path"]
        if len(path) > 90:
            path = "..." + path[-87:]
        table.add_row(f"{item['browser']} {item['type']}", path, format_size(item["size"]))
    for item in tracking_data:
        path = item["path"]
        if len(path) > 90:
            path = "..." + path[-87:]
        table.add_row(item["type"].capitalize(), path, format_size(item["size"]))

    console.print(table)


def view_app_leftovers(leftovers: list):
    """List leftover paths to be deleted."""
    console.print("\n[bold cyan]App leftovers to be deleted:[/bold cyan]")
    table = Table(box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Type", style="cyan")
    table.add_column("Path", style="white")
    table.add_column("Size", justify="right", style="magenta")

    for item in leftovers:
        path = item["path"]
        if len(path) > 90:
            path = "..." + path[-87:]
        table.add_row(item["type"].upper(), path, format_size(item["size"]))

    console.print(table)


def view_optimization_files():
    """Show paths of caches that will be cleared."""
    console.print("\n[bold cyan]Optimization cache folders to be cleared:[/bold cyan]")
    table = Table(box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Target", style="cyan")
    table.add_column("Path", style="white")

    derived_data = Path.home() / "Library" / "Developer" / "Xcode" / "DerivedData"
    pods_cache = Path.home() / ".cocoapods"
    pip_cache = Path.home() / "Library" / "Caches" / "pip"

    for name, path in [("Xcode DerivedData", derived_data), ("CocoaPods Cache", pods_cache), ("Pip Cache", pip_cache)]:
        if path.exists():
            table.add_row(name, str(path))
    console.print(table)


def show_scan_menu() -> str:
    """Show scan action menu."""
    console.print("\n[bold]Actions[/bold]")
    console.print("  [1] Dry Run    [Preview what would be cleaned]")
    console.print("  [2] Clean      [Actually delete files]")
    console.print("  [v] View Files [List all files to be deleted]")
    console.print("  [b] Back")

    return Prompt.ask("\n  Choose", default="1")


def run_system_data_scan():
    """Run system data scan and optional cleanup."""
    console.print("\n[bold cyan]Scanning system data...[/bold cyan]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("Scanning...", total=None)
        results = scan_all()

    show_scan_results(results)

    if not results:
        return

    while True:
        choice = show_scan_menu()
        if choice == "b":
            return
        elif choice == "v":
            view_system_data_files(results)
        elif choice in ("1", "2"):
            break
        else:
            console.print("[red]Invalid choice[/red]")

    dry_run = choice == "1"
    label = "[yellow]DRY RUN[/yellow] - " if dry_run else ""

    console.print(f"\n{label}[bold]Cleaning system data...[/bold]")
    cleanup = clean_system_data(dry_run=dry_run)

    reports = []
    for category, report in cleanup.items():
        print_category_header(category)
        show_delete_report(report)
        reports.append(report)

    total = sum(r.trashed_bytes for r in reports)
    verb = "would be moved to Trash" if dry_run else "moved to Trash"
    console.print(f"\n[bold]Total: ~{format_size(total)} {verb}[/bold]")
    offer_reclaim(reports)


def run_large_files_scan():
    """Run large files scan."""
    console.print("\n[bold cyan]Scanning for large files...[/bold cyan]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("Scanning...", total=None)
        files = find_large_files(min_size_mb=100, max_results=50)

    show_large_files(files)


def run_duplicates_scan():
    """Run duplicates scan."""
    console.print("\n[bold cyan]Scanning for duplicate files...[/bold cyan]")
    console.print("[dim]This may take a while...[/dim]")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("Scanning...", total=None)
        groups = find_duplicates()

    show_duplicates(groups)


def run_snapshots():
    """View and optionally delete snapshots."""
    snapshots = list_snapshots()
    show_snapshots(snapshots)

    if not snapshots:
        return

    while True:
        choice = show_scan_menu()
        if choice == "b":
            return
        elif choice == "v":
            show_snapshots(snapshots)
        elif choice in ("1", "2"):
            break
        else:
            console.print("[red]Invalid choice[/red]")

    dry_run = choice == "1"
    label = "[yellow]DRY RUN[/yellow] - " if dry_run else ""

    if not dry_run:
        print_category_header("snapshots")
        if not confirm_irreversible(f"Deleting {len(snapshots)} snapshot(s)"):
            return

    console.print(f"\n{label}[bold]Deleting snapshots...[/bold]")
    result = clean_snapshots(dry_run=dry_run)
    if dry_run:
        console.print(f"[yellow]Would delete {result.get('count', 0)} snapshot(s)[/yellow]")
    else:
        reclaimed_bytes = result.get("reclaimed_bytes", 0)
        reclaimed_text = (
            "unknown (couldn't isolate the freed space)" if reclaimed_bytes == 0
            else f"~{format_size(reclaimed_bytes)}"
        )
        console.print(f"[green]Deleted: {result.get('deleted', 0)} - "
                      f"Reclaimed {reclaimed_text}[/green]")
        if result.get("failed"):
            console.print(f"[red]Failed: {result.get('failed', 0)}[/red]")


def run_privacy_scan():
    """Run privacy scan and optional cleanup."""
    console.print("\n[bold cyan]Scanning privacy data...[/bold cyan]")
    browser_data = scan_browser_data()
    tracking_data = scan_tracking_data()
    show_privacy_data(browser_data, tracking_data)

    if not browser_data and not tracking_data:
        return

    while True:
        choice = show_scan_menu()
        if choice == "b":
            return
        elif choice == "v":
            view_privacy_files(browser_data, tracking_data)
        elif choice in ("1", "2"):
            break
        else:
            console.print("[red]Invalid choice[/red]")

    dry_run = choice == "1"
    label = "[yellow]DRY RUN[/yellow] - " if dry_run else ""

    console.print(f"\n{label}[bold]Cleaning privacy data...[/bold]")
    result = clean_privacy(dry_run=dry_run)
    reports = []
    for category, report in result.items():
        print_category_header(category)
        show_delete_report(report)
        reports.append(report)
    offer_reclaim(reports)

    # Recents: Irreversible Action, gated separately
    print_category_header("recents")
    if dry_run:
        stats = clear_recently_used(dry_run=True)
        console.print(f"  Would clear {stats['cleared']} recent-items list(s)")
    elif confirm_irreversible("Clearing the recently-used list"):
        stats = clear_recently_used(dry_run=False)
        console.print(f"  [green]Cleared {stats['cleared']} recent-items list(s)[/green]")


def run_app_uninstaller():
    """App uninstaller workflow."""
    apps = get_installed_apps()
    show_apps(apps)

    if not apps:
        return

    app_name = Prompt.ask("Enter app name or list number to uninstall", default="")
    if not app_name:
        return

    # If user entered a number, map it to the corresponding app name in the list
    if app_name.isdigit():
        idx = int(app_name) - 1
        if 0 <= idx < len(apps):
            app_name = apps[idx]["name"]
            console.print(f"[yellow]Resolved selection to: {app_name}[/yellow]")
        else:
            console.print("[red]Invalid selection number[/red]")
            return

    while True:
        choice = show_scan_menu()
        if choice == "b":
            return
        elif choice == "v":
            from scanner.app_remnants import find_leftovers
            try:
                leftovers_list = find_leftovers(app_name)
            except ValueError as e:
                console.print(f"[red]{e}[/red]")
                return
            view_app_leftovers(leftovers_list)
        elif choice in ("1", "2"):
            break
        else:
            console.print("[red]Invalid choice[/red]")

    dry_run = choice == "1"
    label = "[yellow]DRY RUN[/yellow] - " if dry_run else ""

    from cleaner.app_remnants import uninstall_app
    console.print(f"\n{label}[bold]Uninstalling {app_name}...[/bold]")
    try:
        result = uninstall_app(app_name, dry_run=dry_run)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        return
    for key in ("app", "leftovers"):
        report = result[key]
        print_category_header(report.category)
        show_delete_report(report)
    offer_reclaim([result["app"], result["leftovers"]])


def run_optimization():
    """Run optimization tasks."""
    console.print("\n[bold cyan]Running optimization...[/bold cyan]")

    # Show launch agents
    agents = check_launch_agents()
    show_launch_agents(agents)

    while True:
        choice = show_scan_menu()
        if choice == "b":
            return
        elif choice == "v":
            view_optimization_files()
        elif choice in ("1", "2"):
            break
        else:
            console.print("[red]Invalid choice[/red]")

    dry_run = choice == "1"
    label = "[yellow]DRY RUN[/yellow] - " if dry_run else ""

    console.print(f"\n{label}[bold]Optimizing...[/bold]")
    result = optimize_mac(dry_run=dry_run)
    reports = []
    for task, output in result.items():
        if task == "launch_agents":
            continue
        if isinstance(output, DeleteReport):
            print_category_header(output.category)
            show_delete_report(output)
            reports.append(output)
        elif output.get("skipped"):
            console.print(f"  [dim]SKIP[/dim] {task}")
        else:
            print_category_header(task if task in registry.REGISTRY else "brew_cleanup")
            console.print(f"  [green]OK[/green] {task}: {output.get('message', 'Done')}")
    offer_reclaim(reports)


def run_full_scan():
    """Run all scans."""
    console.print("\n[bold cyan]Running full system scan...[/bold cyan]")
    console.print("[dim]This will take a minute...[/dim]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        # System data
        task1 = progress.add_task("[cyan]Scanning system data...", total=None)
        sys_results = scan_all()
        progress.update(task1, description="[green]System data done")

        # Large files
        task2 = progress.add_task("[cyan]Scanning large files...", total=None)
        large = find_large_files(min_size_mb=100, max_results=30)
        progress.update(task2, description="[green]Large files done")

        # Snapshots
        task3 = progress.add_task("[cyan]Checking snapshots...", total=None)
        snaps = list_snapshots()
        progress.update(task3, description="[green]Snapshots done")

        # Privacy
        task4 = progress.add_task("[cyan]Scanning privacy data...", total=None)
        browser = scan_browser_data()
        tracking = scan_tracking_data()
        progress.update(task4, description="[green]Privacy done")

    # Show summary
    console.print("\n" + "=" * 60)
    console.print("[bold yellow]FULL SCAN SUMMARY[/bold yellow]")
    console.print("=" * 60)

    # Disk
    show_disk_overview()

    # System data
    show_scan_results(sys_results)

    # Large files
    if large:
        console.print(f"\n[yellow]Large files found: {len(large)}[/yellow]")
        total_large = sum(f.size for f in large)
        console.print(f"  Total size: {format_size(total_large)}")

    # Snapshots
    if snaps:
        console.print(f"\n[yellow]Local snapshots: {len(snaps)}[/yellow]")
        for s in snaps:
            console.print(f"  {s['name'][:70]}")

    # Privacy
    total_privacy = sum(i["size"] for i in browser + tracking)
    if browser or tracking:
        console.print(f"\n[yellow]Privacy data: {len(browser) + len(tracking)} items ({format_size(total_privacy)})[/yellow]")

    # Duplicates - skip in full scan (too slow)
    console.print("\n[dim]Duplicate scan skipped in full scan mode (use option 3 for dedicated scan)[/dim]")

    console.print("\n[dim]Downloads and iOS backups moved to Space Finder (option 9)[/dim]")


def run_space_finder():
    """Reclaimable User Data: browse -> pick individual items -> confirm."""
    console.print("\n[bold cyan]Scanning reclaimable user data...[/bold cyan]")
    results = scan_space_finder()
    if not results:
        console.print("[green]Nothing found[/green]")
        return

    # Flat numbered list across categories
    flat = []  # (index, category, file_dict)
    for r in results:
        print_category_header(r.category)
        table = Table(box=box.ROUNDED, title=f"{r.name} ({r.human_size})")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Age", justify="right", style="yellow")
        table.add_column("Size", justify="right", style="magenta")
        table.add_column("Path", style="cyan")
        for f in r.files:
            flat.append((len(flat) + 1, r.category, f))
            idx, _, _ = flat[-1]
            table.add_row(str(idx), f"{f['age_days']:.0f}d", format_size(f["size"]),
                          f["path"][-60:])
        console.print(table)

    raw = Prompt.ask("\nEnter item numbers to remove (comma-separated), or blank to cancel",
                     default="")
    if not raw.strip():
        return
    try:
        chosen = {int(x) for x in raw.replace(" ", "").split(",") if x}
    except ValueError:
        console.print("[red]Invalid selection[/red]")
        return

    selected: dict[str, list[dict]] = {}
    for idx, category, f in flat:
        if idx in chosen:
            selected.setdefault(category, []).append(f)
    if not selected:
        console.print("[yellow]No valid items selected[/yellow]")
        return

    from core.deleter import safe_delete
    reports = []
    for category, items in selected.items():
        report = safe_delete(items, category, dry_run=False, user_selected=True)
        print_category_header(category)
        show_delete_report(report)
        reports.append(report)
    offer_reclaim(reports)


def main():
    """Main entry point."""
    print_header()
    show_disk_overview()

    while True:
        try:
            choice = show_main_menu()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold cyan]Goodbye![/bold cyan]")
            break

        if choice == "q":
            console.print("\n[bold cyan]Goodbye![/bold cyan]")
            break
        elif choice == "1":
            run_system_data_scan()
        elif choice == "2":
            run_large_files_scan()
        elif choice == "3":
            run_duplicates_scan()
        elif choice == "4":
            run_snapshots()
        elif choice == "5":
            run_privacy_scan()
        elif choice == "6":
            run_app_uninstaller()
        elif choice == "7":
            run_optimization()
        elif choice == "8":
            run_full_scan()
        elif choice == "9":
            run_space_finder()
        else:
            console.print("[red]Invalid choice[/red]")

        console.print()


if __name__ == "__main__":
    main()
