from ui.app import CleanerApp
from ui.screens.junk import JunkScreen
from ui.screens.space_finder import SpaceFinderScreen


async def test_dashboard_shows_disk_and_navigates(monkeypatch, tmp_path):
    monkeypatch.setattr("ui.screens.dashboard.get_disk_usage",
                        lambda: {"total": 1000, "used": 400, "free": 600,
                                 "percent": 40})
    # keep pushed screens from scanning the real machine
    monkeypatch.setattr("ui.screens.junk.scan_all", lambda: [])
    app = CleanerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "600" in str(app.screen.query_one("#disk", ).content) or \
               "free" in str(app.screen.query_one("#disk").content)
        await pilot.press("1")
        await pilot.pause()
        assert isinstance(app.screen, JunkScreen)
        await pilot.press("escape")
        await pilot.pause()
        monkeypatch.setattr("ui.screens.space_finder.scan_space_finder", lambda: [])
        monkeypatch.setattr("ui.screens.space_finder.find_large_files", lambda **kw: [])
        monkeypatch.setattr("ui.screens.space_finder.find_duplicates", lambda **kw: [])
        await pilot.press("2")
        await pilot.pause()
        assert isinstance(app.screen, SpaceFinderScreen)
