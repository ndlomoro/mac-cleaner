"""The sole renderer for DeleteReports. Wording is bound by CONTEXT.md."""
from textual.widgets import Static

from core.deleter import DeleteReport
from utils.helpers import format_size


def render_report(report: DeleteReport) -> str:
    verb = "Would move to Trash" if report.dry_run else "Moved to Trash"
    lines = [f"[green]{verb}: {len(report.trashed)} items[/green] "
             f"(~{format_size(report.trashed_bytes)})"]
    for r in report.skipped:
        lines.append(f"  [yellow]Skipped:[/yellow] …{r.path[-60:]} - {r.reason}")
    for r in report.failed:
        lines.append(f"  [red]Failed:[/red] …{r.path[-60:]} - {r.reason}")
    return "\n".join(lines)


class ReportView(Static):
    def show(self, reports: list[DeleteReport]) -> None:
        self.update("\n\n".join(render_report(r) for r in reports))
