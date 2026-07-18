import time
from pathlib import Path

from textual.app import App

from scanner.system_data import ScanResult
from ui.screens.junk import JunkScreen


class Host(App):
    def on_mount(self):
        self.push_screen(JunkScreen())


def _fixture_scan(tmp_path):
    f = tmp_path / "old.cache"
    f.write_bytes(b"12345")
    sr = ScanResult("caches", "User Caches")
    sr.add_file(str(f), 5, 30)
    return f, sr


async def test_junk_scan_clean_and_decline_reclaim(tmp_path, monkeypatch, fake_trash):
    f, sr = _fixture_scan(tmp_path)
    monkeypatch.setattr("ui.screens.junk.scan_all", lambda: [sr])

    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()          # let the scan worker post results
        assert host.screen.results   # category arrived
        await pilot.press("c")       # real clean
        await pilot.pause()
        assert not f.exists()
        assert (fake_trash / "old.cache").exists()
        # reclaim gate mounted; escape = decline
        await pilot.press("escape")
        await pilot.pause()
        assert (fake_trash / "old.cache").exists()  # nothing permanently deleted


async def test_junk_dry_run_touches_nothing(tmp_path, monkeypatch, fake_trash):
    f, sr = _fixture_scan(tmp_path)
    monkeypatch.setattr("ui.screens.junk.scan_all", lambda: [sr])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        assert f.exists()
        report_text = str(host.screen.query_one("#report").content)
        assert "Would move to Trash" in report_text


async def test_worker_error_resets_busy_and_notifies(tmp_path, monkeypatch, fake_trash):
    f, sr = _fixture_scan(tmp_path)
    monkeypatch.setattr("ui.screens.junk.scan_all", lambda: [sr])
    def _boom(res, dry_run=False):
        raise RuntimeError("cleaner exploded")
    monkeypatch.setattr("ui.screens.junk.clean_files", _boom)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        await pilot.pause()
        assert host.screen._cleaning is False   # flag reset, screen usable


async def test_junk_preview_toggle(tmp_path, monkeypatch, fake_trash):
    f, sr = _fixture_scan(tmp_path)
    monkeypatch.setattr("ui.screens.junk.scan_all", lambda: [sr])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("v")
        await pilot.pause()
        text = str(host.screen.query_one("#preview").content)
        # render_paths truncates long paths to their last 76 chars ("…" prefix)
        assert str(f)[-76:] in text
        await pilot.press("v")
        await pilot.pause()
        text2 = str(host.screen.query_one("#preview").content)
        assert text2 == ""


async def test_junk_preview_clears_after_real_clean(tmp_path, monkeypatch, fake_trash):
    f, sr = _fixture_scan(tmp_path)
    monkeypatch.setattr("ui.screens.junk.scan_all", lambda: [sr])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("v")       # preview on - lists the now-stale path
        await pilot.pause()
        assert str(f)[-76:] in str(host.screen.query_one("#preview").content)
        await pilot.press("c")       # real clean - trashes the item, then
                                      # offers the reclaim gate (TypedGateModal
                                      # is now on top of the screen stack)
        await pilot.pause()
        junk_screen = host.screen_stack[-2]
        assert str(junk_screen.query_one("#preview").content) == ""
        assert junk_screen._preview_shown is False


async def test_double_press_does_not_double_clean(tmp_path, monkeypatch, fake_trash):
    f, sr = _fixture_scan(tmp_path)
    monkeypatch.setattr("ui.screens.junk.scan_all", lambda: [sr])
    calls = []
    real_clean = __import__("ui.screens.junk", fromlist=["clean_files"]).clean_files
    def counting_clean(res, dry_run=False):
        calls.append(1)
        time.sleep(0.05)  # keep the worker "in flight" across both key presses
        return real_clean(res, dry_run=dry_run)
    monkeypatch.setattr("ui.screens.junk.clean_files", counting_clean)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("d", "d")
        await pilot.pause()
        await pilot.pause()
    assert len(calls) == 1
