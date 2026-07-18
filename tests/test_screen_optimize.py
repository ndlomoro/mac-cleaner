from textual.app import App

from core.deleter import DeleteReport
from ui.screens.optimize import OptimizeScreen


class Host(App):
    def on_mount(self):
        self.push_screen(OptimizeScreen())


async def test_optimize_renders_reports_and_external_labels(monkeypatch, fake_trash):
    result = {
        "pip_cache": DeleteReport("pip_cache", dry_run=True),
        "brew_cleanup": {"message": "Cleaned up", "skipped": False},
        "xcode_derived_data": {"message": "No xcode_derived_data found",
                               "skipped": True},
    }
    monkeypatch.setattr("ui.screens.optimize.optimize_mac",
                        lambda dry_run: result)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        text = str(host.screen.query_one("#optimize-log").content)
        assert "Would move to Trash" in text          # DeleteReport rendering
        assert "not recoverable via Trash" in text    # external-tool label
        assert "SKIP" in text
