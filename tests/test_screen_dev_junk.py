from pathlib import Path as P

from textual.app import App
from textual.widgets import SelectionList, Static

from ui.screens.dev_junk import DevJunkScreen
from utils.helpers import format_size


class Host(App):
    def on_mount(self):
        self.push_screen(DevJunkScreen())


def _row(path, size=10, age_days=400, kind="node_modules", project="foo"):
    return {"path": str(path), "size": size, "age_days": age_days,
            "kind": kind, "project": project}


async def test_nothing_preselected_and_no_select_all(tmp_path, monkeypatch, fake_trash):
    f = tmp_path / "node_modules"
    f.mkdir()
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts",
                        lambda: [_row(f)])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        sel = host.screen.query_one("#list-artifacts", SelectionList)
        assert sel.selected == []
        bound_keys = {b[0] if isinstance(b, tuple) else b.key
                      for b in host.screen.BINDINGS}
        assert "a" not in bound_keys  # no select-all affordance


async def test_pick_confirm_trash(tmp_path, monkeypatch, fake_trash):
    f = tmp_path / "node_modules"
    f.mkdir()
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts",
                        lambda: [_row(f)])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        sel = host.screen.query_one("#list-artifacts", SelectionList)
        sel.focus()
        await pilot.press("space")     # select the only row
        await pilot.press("t")         # Move to Trash -> ConfirmModal
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()
        assert not f.exists()
        assert (fake_trash / "node_modules").exists()

        # Reclaim offer: decline -> file stays in Trash
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert (fake_trash / "node_modules").exists()


async def test_pick_confirm_trash_then_reclaim_confirmed(tmp_path, monkeypatch, fake_trash):
    f = tmp_path / "node_modules"
    f.mkdir()
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts",
                        lambda: [_row(f)])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        sel = host.screen.query_one("#list-artifacts", SelectionList)
        sel.focus()
        await pilot.press("space")
        await pilot.press("t")
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()
        assert not f.exists()
        assert (fake_trash / "node_modules").exists()

        # Reclaim offer: confirm by typing yes -> permanently gone
        await pilot.pause()
        for ch in "yes":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert not (fake_trash / "node_modules").exists()


async def test_decline_leaves_everything(tmp_path, monkeypatch, fake_trash):
    f = tmp_path / "node_modules"
    f.mkdir()
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts",
                        lambda: [_row(f)])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        host.screen.query_one("#list-artifacts", SelectionList).focus()
        await pilot.press("space", "t")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert f.exists()


async def test_skipped_items_stay_listed(tmp_path, monkeypatch, fake_trash):
    good = tmp_path / "node_modules"
    good.mkdir()
    hard = P.home() / ".ssh" / "id_ed25519"   # hard-protected -> SKIPPED
    rows = [_row(good), _row(hard, size=5, age_days=900, kind="venv", project="ssh")]
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts", lambda: rows)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        sel = host.screen.query_one("#list-artifacts", SelectionList)
        sel.select(0); sel.select(1)
        await pilot.press("t"); await pilot.pause()
        await pilot.click("#confirm"); await pilot.pause()
        await pilot.press("escape"); await pilot.pause()   # decline reclaim offer
        remaining = {it["path"] for it in host.screen.items.values()}
        assert str(hard) in remaining          # skipped item still listed
        assert str(good) not in remaining      # trashed item removed


async def test_selected_total_footer_updates_and_resets(tmp_path, monkeypatch, fake_trash):
    f = tmp_path / "node_modules"
    f.mkdir()
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts",
                        lambda: [_row(f, size=10)])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        footer = host.screen.query_one("#sel-total", Static)
        assert "Nothing selected" in footer.content

        sel = host.screen.query_one("#list-artifacts", SelectionList)
        sel.focus()
        await pilot.press("space")     # select the only row (size=10)
        await pilot.pause()
        assert "1 item" in footer.content
        assert format_size(10) in footer.content

        await pilot.press("t")         # Move to Trash -> ConfirmModal
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()
        assert not f.exists()
        # selections were cleared by the trash pass - footer resets
        assert "Nothing selected" in footer.content
