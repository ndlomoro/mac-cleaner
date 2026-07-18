from textual.app import App

from ui.screens.snapshots import SnapshotsScreen


class Host(App):
    def on_mount(self):
        self.push_screen(SnapshotsScreen())


async def test_snapshot_delete_gated_and_reports_reclaimed(monkeypatch):
    monkeypatch.setattr("ui.screens.snapshots.list_snapshots",
                        lambda: [{"name": "com.apple.TimeMachine.x.local"}])
    calls = []
    monkeypatch.setattr(
        "ui.screens.snapshots.clean_snapshots",
        lambda dry_run=False: calls.append(1) or
        {"deleted": 1, "failed": 0, "successes": ["x"], "failures": [],
         "reclaimed_bytes": 500})
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("escape")          # decline gate
        await pilot.pause()
        assert calls == []
        await pilot.press("x")
        await pilot.pause()
        await pilot.click("#gate-input")
        await pilot.press(*"yes", "enter")   # pass gate
        await pilot.pause()
        assert calls == [1]
        text = str(host.screen.query_one("#snap-log").content)
        assert "Reclaimed" in text and "500" in text


async def test_snapshot_zero_delta_shows_unknown(monkeypatch):
    monkeypatch.setattr("ui.screens.snapshots.list_snapshots",
                        lambda: [{"name": "s"}])
    monkeypatch.setattr(
        "ui.screens.snapshots.clean_snapshots",
        lambda dry_run=False: {"deleted": 1, "failed": 0, "successes": ["x"],
                               "failures": [], "reclaimed_bytes": 0})
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("x")
        await pilot.pause()
        await pilot.click("#gate-input")
        await pilot.press(*"yes", "enter")
        await pilot.pause()
        text = str(host.screen.query_one("#snap-log").content)
        assert "unknown" in text.lower()
