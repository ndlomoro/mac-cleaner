from textual.app import App
from textual.widgets import SelectionList

from scanner.system_data import ScanResult
from ui.screens.space_finder import SpaceFinderScreen


class Host(App):
    def on_mount(self):
        self.push_screen(SpaceFinderScreen())


def _patch_scanners(monkeypatch, tmp_path, dup_paths=()):
    dl = ScanResult("downloads", "Downloads")
    f = tmp_path / "old.dmg"
    f.write_bytes(b"x" * 10)
    dl.add_file(str(f), 10, 400)
    monkeypatch.setattr("ui.screens.space_finder.scan_space_finder", lambda: [dl])
    monkeypatch.setattr("ui.screens.space_finder.find_large_files",
                        lambda **kw: [])
    groups = []
    if dup_paths:
        groups = [{"hash": "h1", "size": 4,
                   "files": [str(p) for p in dup_paths],
                   "wasted": 4 * (len(dup_paths) - 1)}]
    monkeypatch.setattr("ui.screens.space_finder.find_duplicates",
                        lambda **kw: groups)
    return f


async def test_nothing_preselected_and_no_select_all(tmp_path, monkeypatch, fake_trash):
    _patch_scanners(monkeypatch, tmp_path)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        for sl in host.screen.query(SelectionList):
            assert sl.selected == []
        bound_keys = {b[0] if isinstance(b, tuple) else b.key
                      for b in host.screen.BINDINGS}
        assert "a" not in bound_keys  # no select-all affordance


async def test_pick_confirm_trash(tmp_path, monkeypatch, fake_trash):
    f = _patch_scanners(monkeypatch, tmp_path)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        dl_list = host.screen.query_one("#list-downloads", SelectionList)
        dl_list.focus()
        await pilot.press("space")     # select the only row
        await pilot.press("t")         # Move to Trash -> ConfirmModal
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()
        assert not f.exists()
        assert (fake_trash / "old.dmg").exists()

        # Reclaim offer (parity with Junk screen): decline -> file stays in Trash
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert (fake_trash / "old.dmg").exists()


async def test_pick_confirm_trash_then_reclaim_confirmed(tmp_path, monkeypatch, fake_trash):
    f = _patch_scanners(monkeypatch, tmp_path)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        dl_list = host.screen.query_one("#list-downloads", SelectionList)
        dl_list.focus()
        await pilot.press("space")
        await pilot.press("t")
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()
        assert not f.exists()
        assert (fake_trash / "old.dmg").exists()

        # Reclaim offer: confirm by typing yes -> permanently gone
        await pilot.pause()
        for ch in "yes":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert not (fake_trash / "old.dmg").exists()


async def test_decline_leaves_everything(tmp_path, monkeypatch, fake_trash):
    f = _patch_scanners(monkeypatch, tmp_path)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        host.screen.query_one("#list-downloads", SelectionList).focus()
        await pilot.press("space", "t")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert f.exists()


async def test_skipped_items_stay_listed(tmp_path, monkeypatch, fake_trash):
    from pathlib import Path as P

    from scanner.system_data import ScanResult
    dl = ScanResult("downloads", "Downloads")
    good = tmp_path / "old.dmg"; good.write_bytes(b"x" * 10)
    hard = P.home() / ".ssh" / "id_ed25519"   # hard-protected -> SKIPPED
    dl.add_file(str(good), 10, 400)
    dl.add_file(str(hard), 5, 900)
    monkeypatch.setattr("ui.screens.space_finder.scan_space_finder", lambda: [dl])
    monkeypatch.setattr("ui.screens.space_finder.find_large_files", lambda **kw: [])
    monkeypatch.setattr("ui.screens.space_finder.find_duplicates", lambda **kw: [])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        sel = host.screen.query_one("#list-downloads", SelectionList)
        sel.select(0); sel.select(1)
        await pilot.press("t"); await pilot.pause()
        await pilot.click("#confirm"); await pilot.pause()
        await pilot.press("escape"); await pilot.pause()   # decline reclaim offer
        remaining = {it["path"] for it in host.screen.items["downloads"].values()}
        assert str(hard) in remaining          # skipped item still listed
        assert str(good) not in remaining      # trashed item removed


async def test_keep_one_invariant(tmp_path, monkeypatch, fake_trash):
    a = tmp_path / "a.jpg"; a.write_bytes(b"1234")
    b = tmp_path / "b.jpg"; b.write_bytes(b"1234")
    _patch_scanners(monkeypatch, tmp_path, dup_paths=(a, b))
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        dup_list = host.screen.query_one("#list-duplicates", SelectionList)
        dup_list.focus()
        await pilot.press("space")          # select copy 1 - fine
        await pilot.press("down", "space")  # try to select copy 2 - refused
        await pilot.pause()
        assert len(dup_list.selected) == 1  # one copy always kept
