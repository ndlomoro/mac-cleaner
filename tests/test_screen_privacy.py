from textual.app import App

from core.deleter import DeleteReport
from ui.screens.privacy import PrivacyScreen


class Host(App):
    def on_mount(self):
        self.push_screen(PrivacyScreen())


async def test_privacy_clean_shows_reports(monkeypatch, fake_trash):
    empty = {"browser_cache": DeleteReport("browser_cache", dry_run=True),
             "tracking_data": DeleteReport("tracking_data", dry_run=True)}
    monkeypatch.setattr("ui.screens.privacy.clean_privacy",
                        lambda dry_run: empty)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        text = str(host.screen.query_one("#report").content)
        assert "Would move to Trash" in text


async def test_privacy_preview_filters_history_and_byhost(monkeypatch):
    monkeypatch.setattr(
        "ui.screens.privacy.scan_browser_data",
        lambda: [
            {"browser": "Safari", "type": "caches", "path": "/caches/safari", "size": 1},
            {"browser": "Safari", "type": "history", "path": "/history/safari.db", "size": 1},
        ],
    )
    monkeypatch.setattr(
        "ui.screens.privacy.scan_tracking_data",
        lambda: [
            {"type": "tracking_dir", "path": "/tracking/diag", "size": 1},
            {"type": "tracking_file",
             "path": "/Library/Preferences/ByHost/x.plist", "size": 1},
        ],
    )
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        text = str(host.screen.query_one("#preview").content)
        assert "/caches/safari" in text
        assert "/history/safari.db" not in text
        assert "/tracking/diag" in text
        assert "ByHost" not in text
        await pilot.press("v")
        await pilot.pause()
        assert str(host.screen.query_one("#preview").content) == ""


async def test_recents_gate_blocks_without_yes(monkeypatch):
    calls = []
    monkeypatch.setattr("ui.screens.privacy.clear_recently_used",
                        lambda dry_run=False: calls.append(dry_run) or
                        {"cleared": 1, "failed": 0})
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        await pilot.press("escape")   # decline the typed gate
        await pilot.pause()
    assert calls == []  # never invoked without the gate
