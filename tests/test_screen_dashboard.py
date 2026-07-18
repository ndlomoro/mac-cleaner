from ui.app import CleanerApp
from ui.screens.junk import JunkScreen
from ui.screens.space_finder import SpaceFinderScreen


async def test_dashboard_shows_disk_and_navigates(monkeypatch):
    monkeypatch.setattr("ui.screens.dashboard.get_disk_usage",
                        lambda: {"total": 1000, "used": 400, "free": 600,
                                 "percent": 40})
    # keep pushed screens from scanning the real machine
    monkeypatch.setattr("ui.screens.junk.scan_all", lambda: [])
    app = CleanerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "600" in str(app.screen.query_one("#disk").content) or \
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


async def test_dashboard_survives_disk_stat_failure(monkeypatch):
    # get_disk_usage() returns {} on OSError (see utils/helpers.py); the app
    # must still boot instead of crashing on a KeyError in on_mount.
    monkeypatch.setattr("ui.screens.dashboard.get_disk_usage", lambda: {})
    app = CleanerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "unavailable" in str(app.screen.query_one("#disk").content)


async def test_quick_scan_summarizes(monkeypatch, tmp_path):
    from scanner.system_data import ScanResult
    monkeypatch.setattr("ui.screens.dashboard.get_disk_usage",
                        lambda: {"total": 1000, "used": 400, "free": 600, "percent": 40})
    sr = ScanResult("caches", "User Caches")
    f = tmp_path / "c.bin"; f.write_bytes(b"x" * 50)
    sr.add_file(str(f), 50, 10)
    monkeypatch.setattr("ui.screens.dashboard.scan_all", lambda: [sr])
    monkeypatch.setattr("ui.screens.dashboard.scan_space_finder", lambda: [])
    from ui.app import CleanerApp
    app = CleanerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.pause()
        text = str(app.screen.query_one("#summary").content)
        assert "User Caches" in text and "1 items" in text
