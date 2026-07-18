"""Optimize screen - dev caches (via Trash) + brew/npm (external tools)."""
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from cleaner.optimization import DERIVED_DATA, PIP_CACHE, PODS_CACHE, optimize_mac
from core.deleter import DeleteReport
from scanner.optimization import check_launch_agents
from ui.screens._util import run_offthread
from ui.widgets.category_header import CategoryHeader, header_markup
from ui.widgets.report_view import render_report


class OptimizeScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("d", "dry_run", "Dry Run"),
        ("c", "clean", "Optimize"),
        ("v", "toggle_preview", "View Files"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static(id="optimize-log")
            yield Static(id="preview")
            yield CategoryHeader("launch_agents")
            yield Static(id="agents")
        yield Footer()

    def on_mount(self) -> None:
        self._optimizing = False
        self._preview_shown = False
        self.query_one("#agents", Static).update("Scanning…")

        def _work():
            return check_launch_agents()

        def _done(agents: list[dict]) -> None:
            if not agents:
                self.query_one("#agents", Static).update(
                    "No third-party launch agents found.")
                return
            lines = [f"{a['name']} ({a['path']})" for a in agents]
            self.query_one("#agents", Static).update("\n".join(lines))

        def _error(e: Exception) -> None:
            self.notify(f"Failed to list launch agents: {e}", severity="error")

        run_offthread(self, _work, _done, _error)

    def action_toggle_preview(self) -> None:
        preview = self.query_one("#preview", Static)
        if self._preview_shown:
            preview.update("")
            self._preview_shown = False
            return
        lines = ["[bold]Dev caches (via Trash)[/bold]"]
        for label, path in [
            ("Xcode DerivedData", DERIVED_DATA),
            ("CocoaPods cache", PODS_CACHE),
            ("pip cache", PIP_CACHE),
        ]:
            marker = "exists" if path.exists() else "missing"
            lines.append(f"  {label}: {path} ({marker})")
        lines.append("[dim]brew cleanup and npm cache are external tools, "
                     "cleaned directly - not shown here[/dim]")
        preview.update("\n".join(lines))
        self._preview_shown = True

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
                elif output.get("error"):
                    message = output.get("message", output["error"])
                    lines.append(f"[red]FAILED[/red] {task}: {message}")
                elif output.get("skipped"):
                    lines.append(f"[dim]SKIP[/dim] {task}")
                else:
                    lines.append(header_markup(task))
                    lines.append(f"  [green]OK[/green] {output.get('message', 'Done')}")
            self.query_one("#optimize-log", Static).update("\n".join(lines))
            self._optimizing = False

        def _error(e: Exception) -> None:
            self._optimizing = False
            self.notify(f"Failed: {e}", severity="error")

        run_offthread(self, _work, _done, _error)
