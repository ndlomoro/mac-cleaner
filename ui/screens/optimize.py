"""Optimize screen - dev caches (via Trash) + brew/npm (external tools)."""
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from cleaner.optimization import optimize_mac
from core.deleter import DeleteReport
from ui.widgets.category_header import header_markup
from ui.widgets.report_view import render_report


class OptimizeScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("d", "dry_run", "Dry Run"),
        ("c", "clean", "Optimize"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(Static(id="optimize-log"))
        yield Footer()

    def on_mount(self) -> None:
        self._optimizing = False

    def action_dry_run(self) -> None:
        self._run(dry_run=True)

    def action_clean(self) -> None:
        self._run(dry_run=False)

    def _run(self, dry_run: bool) -> None:
        if self._optimizing:
            self.notify("Already running…")
            return
        self._optimizing = True

        def _work():
            return optimize_mac(dry_run=dry_run)

        def _done(result: dict) -> None:
            lines = []
            for task, output in result.items():
                if task == "launch_agents":
                    continue
                if isinstance(output, DeleteReport):
                    lines.append(header_markup(output.category))
                    lines.append(render_report(output))
                elif output.get("skipped"):
                    lines.append(f"[dim]SKIP[/dim] {task}")
                else:
                    lines.append(header_markup(task))
                    lines.append(f"  [green]OK[/green] {output.get('message', 'Done')}")
            self.query_one("#optimize-log", Static).update("\n".join(lines))
            self._optimizing = False

        self.run_worker(lambda: self.app.call_from_thread(_done, _work()),
                        thread=True)
