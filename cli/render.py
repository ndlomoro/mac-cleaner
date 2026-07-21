"""Pure renderers for the CLI. No I/O - functions return Rich renderables or
plain strings so they can be unit-tested without a terminal.

The DeleteReport formatting is deliberately truthful (CONTEXT.md): moving to
the Trash is reported as "Trashed", never "freed"/"cleaned"; only reclaim()
earns the word "Reclaimed".
"""
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from core.deleter import DeleteReport
from core.registry import Category, Level
from utils.helpers import format_size, get_disk_usage

LEVEL_STYLES = {Level.SAFE: "green", Level.CAUTION: "yellow", Level.RISKY: "red"}


def tail(path: str, n: int = 60) -> str:
    """Right-anchored path, prefixed with an ellipsis when truncated."""
    return path if len(path) <= n else f"…{path[-n:]}"


def level_tag(level: Level) -> Text:
    """Coloured [SAFE]/[CAUTION]/[RISKY] badge."""
    return Text(f"[{level.value}]", style=LEVEL_STYLES[level])


def category_header(cat: Category) -> Text:
    """Level badge + plain-English explanation; flags non-Trash categories."""
    line = level_tag(cat.level)
    line.append(" ")
    line.append(cat.explanation)
    if not cat.via_trash:
        line.append("  (cleared directly - not recoverable via Trash)",
                     style="dim")
    return line


def disk_panel() -> Panel:
    """Disk overview header for the top of the menu."""
    usage = get_disk_usage()
    if not usage:
        return Panel("Could not read disk info", title="Mac Cleaner",
                     border_style="cyan")
    pct = usage["percent"]
    pct_style = "green" if pct < 70 else ("yellow" if pct < 90 else "red")
    body = Text()
    body.append(f"{format_size(usage['total'])} total  ·  ")
    body.append(f"{format_size(usage['free'])} free  ·  ")
    body.append(f"{pct}% used", style=pct_style)
    return Panel(body, title="Mac Cleaner", border_style="cyan")


def scan_table(results: list) -> Table:
    """Category / Items / Size table for a set of ScanResults, with a TOTAL."""
    table = Table(title="Scan results", header_style="bold")
    table.add_column("Category", style="cyan")
    table.add_column("Items", justify="right")
    table.add_column("Size", justify="right", style="magenta")
    total_size = 0
    total_files = 0
    for r in results:
        table.add_row(r.name, str(r.file_count), r.human_size)
        total_size += r.total_size
        total_files += r.file_count
    table.add_row("[bold]TOTAL[/bold]", f"[bold]{total_files}[/bold]",
                  f"[bold]{format_size(total_size)}[/bold]")
    return table


def rows_table(title: str, items: dict[int, dict], selected: set[int],
               keeper_aware: bool = False) -> Table:
    """Numbered, selectable rows for one Space Finder / Dev Junk category.

    `items` maps a 1-based display number to a scanned item dict. Rows the
    user has selected get a ✓; duplicate keepers get a ★ when keeper_aware.
    """
    table = Table(title=title, header_style="bold")
    table.add_column("#", justify="right", style="dim")
    table.add_column("", width=1)  # selection / keeper marker
    table.add_column("Size", justify="right", style="magenta")
    table.add_column("Age", justify="right", style="yellow")
    table.add_column("Path")
    for num in sorted(items):
        item = items[num]
        mark = "✓" if num in selected else ""
        if keeper_aware and item.get("path") == item.get("keeper"):
            mark = mark or "★"
        age = item.get("age_days")
        age_str = f"{age:.0f}d" if isinstance(age, (int, float)) else "—"
        table.add_row(str(num), mark, format_size(item.get("size", 0)),
                      age_str, tail(item.get("path", ""), 64))
    return table


def report_lines(report: DeleteReport) -> list[str]:
    """Truthful, style-free summary lines for one DeleteReport.

    First line uses "Would move to Trash" (dry run) or "Moved to Trash";
    never "freed". Skipped/failed items are listed with their reason so a
    partial result is never mistaken for a clean sweep.
    """
    verb = "Would move to Trash" if report.dry_run else "Moved to Trash"
    lines = [f"{verb}: {len(report.trashed)} item(s) "
             f"(~{format_size(report.trashed_bytes)})"]
    for r in report.skipped:
        lines.append(f"Skipped: {tail(r.path)} - {r.reason}")
    for r in report.failed:
        lines.append(f"Failed: {tail(r.path)} - {r.reason}")
    return lines


def reports_lines(reports: list[DeleteReport]) -> list[str]:
    """report_lines for several reports, each prefixed with its category."""
    out: list[str] = []
    for report in reports:
        for i, line in enumerate(report_lines(report)):
            out.append(f"[{report.category}] {line}" if i == 0 else f"  {line}")
    return out
