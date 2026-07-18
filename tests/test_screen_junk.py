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
