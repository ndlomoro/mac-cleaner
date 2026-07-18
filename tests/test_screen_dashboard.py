from ui.app import CleanerApp
from ui.screens.dev_junk import DevJunkScreen
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


async def test_disk_line_refreshes_on_resume(monkeypatch):
    """Screen-resume rescans: the dashboard's disk line must refresh when the
    user returns from a sub-screen (e.g. after cleaning elsewhere frees space)
    without re-running the explicit Quick Scan action."""
    calls = []

    def _counting_disk_usage():
        calls.append(1)
        return {"total": 1000, "used": 400, "free": 600, "percent": 40}

    monkeypatch.setattr("ui.screens.dashboard.get_disk_usage", _counting_disk_usage)
    monkeypatch.setattr("ui.screens.junk.scan_all", lambda: [])
    app = CleanerApp()
    async with app.run_test() as pilot:
        await pilot.press("1")       # dashboard -> Junk
        await pilot.pause()
        await pilot.press("escape")  # Junk -> dashboard: resume refresh
        await pilot.pause()
    assert len(calls) >= 2


async def test_quick_scan_summarizes(monkeypatch, tmp_path):
    from scanner.system_data import ScanResult
    monkeypatch.setattr("ui.screens.dashboard.get_disk_usage",
                        lambda: {"total": 1000, "used": 400, "free": 600, "percent": 40})
    sr = ScanResult("caches", "User Caches")
    f = tmp_path / "c.bin"; f.write_bytes(b"x" * 50)
    sr.add_file(str(f), 50, 10)
    monkeypatch.setattr("ui.screens.dashboard.scan_all", lambda: [sr])
    monkeypatch.setattr("ui.screens.dashboard.scan_space_finder", lambda: [])
    monkeypatch.setattr("ui.screens.dashboard.find_project_artifacts",
                         lambda: [
                             {"path": "/p1/node_modules", "size": 100,
                              "age_days": 1, "kind": "node_modules", "project": "p1"},
                             {"path": "/p1/.venv", "size": 200,
                              "age_days": 1, "kind": "venv", "project": "p1"},
                             {"path": "/p2/target", "size": 50,
                              "age_days": 1, "kind": "rust_target", "project": "p2"},
                         ])
    from ui.app import CleanerApp
    app = CleanerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.pause()
        text = str(app.screen.query_one("#summary").content)
        assert "User Caches" in text and "1 items" in text
        assert "Dev junk:" in text and "2 projects" in text


async def test_quick_scan_omits_dev_junk_line_when_empty(monkeypatch, tmp_path):
    from scanner.system_data import ScanResult
    monkeypatch.setattr("ui.screens.dashboard.get_disk_usage",
                        lambda: {"total": 1000, "used": 400, "free": 600, "percent": 40})
    sr = ScanResult("caches", "User Caches")
    f = tmp_path / "c.bin"; f.write_bytes(b"x" * 50)
    sr.add_file(str(f), 50, 10)
    monkeypatch.setattr("ui.screens.dashboard.scan_all", lambda: [sr])
    monkeypatch.setattr("ui.screens.dashboard.scan_space_finder", lambda: [])
    monkeypatch.setattr("ui.screens.dashboard.find_project_artifacts", lambda: [])
    app = CleanerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("s")
        await pilot.pause()
        await pilot.pause()
        text = str(app.screen.query_one("#summary").content)
        assert "Dev junk:" not in text


async def test_dashboard_navigates_to_dev_junk(monkeypatch):
    monkeypatch.setattr("ui.screens.dashboard.get_disk_usage",
                        lambda: {"total": 1000, "used": 400, "free": 600,
                                 "percent": 40})
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts", lambda: [])
    monkeypatch.setattr("ui.screens.dev_junk.find_docker_junk", lambda: None)
    monkeypatch.setattr("ui.screens.dev_junk.find_simulators", lambda: [])
    app = CleanerApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("7")
        await pilot.pause()
        assert isinstance(app.screen, DevJunkScreen)
