import asyncio
import time

from textual.app import App

from scanner.system_data import ScanResult
from ui.app import CleanerApp
from ui.screens.junk import JunkScreen
from ui.widgets.category_header import CategoryHeader


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


async def test_revisiting_junk_screen_rescans(monkeypatch):
    """Screen-resume rescans: returning to Junk from the dashboard must
    re-run scan_all so counts reflect any cleaning done elsewhere. Textual
    fires on_screen_resume once right after the initial on_mount too - that
    first resume must be swallowed so a fresh push still scans exactly once."""
    calls = []

    def _counting_scan_all():
        calls.append(1)
        return []

    monkeypatch.setattr("ui.screens.junk.scan_all", _counting_scan_all)
    app = CleanerApp()
    async with app.run_test() as pilot:
        await pilot.press("1")       # dashboard -> Junk: initial mount scan
        await pilot.pause()
        await pilot.press("escape")  # Junk -> dashboard
        await pilot.pause()
        await pilot.press("1")       # dashboard -> Junk again: resume rescan
        await pilot.pause()
    assert calls == [1, 1]


async def test_resume_during_reclaim_worker_does_not_rescan(tmp_path, monkeypatch, fake_trash):
    """Critical busy-coverage gap: _cleaning was cleared before the reclaim
    gate was even answered, so navigating away and back while the reclaim
    worker was still running fired a resume-triggered rescan. _cleaning must
    stay True through the reclaim gate + reclaim worker, clearing only in
    reclaim's terminal callback."""
    f, sr = _fixture_scan(tmp_path)
    scan_calls = []

    def counting_scan_all():
        scan_calls.append(1)
        return [sr]

    monkeypatch.setattr("ui.screens.junk.scan_all", counting_scan_all)

    real_reclaim = __import__("ui.screens.junk", fromlist=["reclaim"]).reclaim

    def slow_reclaim(reports):
        time.sleep(0.3)
        return real_reclaim(reports)

    monkeypatch.setattr("ui.screens.junk.reclaim", slow_reclaim)

    app = CleanerApp()
    async with app.run_test() as pilot:
        await pilot.press("1")
        await pilot.pause()                   # initial scan -> call #1
        await pilot.press("c")                # real clean -> trashes -> reclaim gate
        await pilot.pause()
        await pilot.click("#gate-input")
        await pilot.press(*"yes", "enter")    # confirm reclaim -> slow worker starts
        await pilot.press("escape")           # navigate away mid-reclaim
        await pilot.pause()
        await pilot.press("1")                # re-enter mid-reclaim - must NOT rescan
        await pilot.pause()
        assert scan_calls == [1]              # busy flag held through reclaim

        await asyncio.sleep(0.4)              # let reclaim land, clearing _cleaning
        await pilot.pause()

        # a genuine resume AFTER the busy flag clears must rescan normally
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
    assert scan_calls == [1, 1]


async def test_reentry_mid_scan_does_not_double_scan(monkeypatch):
    """Minor closed on re-review: junk's INITIAL scan had no covering flag,
    so backing out and re-entering while scan_all() was still running fired
    a second concurrent scan worker - reviewer reproduced doubled
    CategoryHeader widgets. _scanning must guard the resume the same way
    the destructive-flow busy flags do."""
    def _slow_scan_all():
        time.sleep(0.3)
        sr = ScanResult("caches", "User Caches")
        return [sr]

    monkeypatch.setattr("ui.screens.junk.scan_all", _slow_scan_all)
    app = CleanerApp()
    async with app.run_test() as pilot:
        await pilot.press("1")        # dashboard -> Junk: slow scan starts
        await pilot.pause()
        await pilot.press("escape")   # navigate away mid-scan
        await pilot.pause()
        await pilot.press("1")        # re-enter mid-scan - must NOT rescan
        await pilot.pause()
        await asyncio.sleep(0.4)      # let the slow scan land
        await pilot.pause()
        await pilot.pause()
        headers = app.screen.query(CategoryHeader)
        assert len(headers) == 1      # exactly one per category, no duplicates
