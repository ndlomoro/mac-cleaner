import asyncio
import time
from pathlib import Path as P

from textual.app import App
from textual.css.query import NoMatches
from textual.widgets import SelectionList, Static

import ui.screens.dev_junk as dev_junk_mod
from ui.screens.dev_junk import DevJunkScreen
from utils.helpers import format_size


class Host(App):
    def on_mount(self):
        self.push_screen(DevJunkScreen())


def _row(path, size=10, age_days=400, kind="node_modules", project="foo"):
    return {"path": str(path), "size": size, "age_days": age_days,
            "kind": kind, "project": project}


def _docker_dict(images=1_000_000_000, volumes=2_000_000_000, build_cache=3_000_000_000):
    return {"images_bytes": images, "volumes_bytes": volumes,
            "build_cache_bytes": build_cache}


def _sim(name="iPhone 8", udid="ABC-123"):
    return {"name": name, "kind": "device", "size": 0, "udid": udid}


class _RunCommandRecorder:
    """run_command stand-in: records argv, always returns docker's own
    success-with-a-figure shape so the "Reclaimed" wording has something
    truthful to report."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, argv, sudo=False):
        self.calls.append(list(argv))
        return "Total reclaimed space: 8GB", "", 0


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


# ---------- Docker / Simulators zones ----------

def _patch_docker_sims(monkeypatch, docker=None, sims=None):
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts", lambda: [])
    monkeypatch.setattr("ui.screens.dev_junk.find_docker_junk", lambda: docker)
    monkeypatch.setattr("ui.screens.dev_junk.find_simulators", lambda: sims or [])
    recorder = _RunCommandRecorder()
    monkeypatch.setattr("ui.screens.dev_junk.run_command", recorder)
    return recorder


async def test_docker_and_sim_gate_refusal(monkeypatch, fake_trash):
    recorder = _patch_docker_sims(monkeypatch, docker=_docker_dict(), sims=[_sim()])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()

        await pilot.press("D")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert recorder.calls == []

        await pilot.press("S")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert recorder.calls == []


async def test_docker_prune_declines_volumes_by_default(monkeypatch, fake_trash):
    recorder = _patch_docker_sims(monkeypatch, docker=_docker_dict())
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()

        await pilot.press("D")
        await pilot.pause()
        for ch in "yes":
            await pilot.press(ch)
        await pilot.press("enter")     # TypedGateModal confirmed -> volumes ConfirmModal
        await pilot.pause()
        await pilot.press("escape")    # decline volumes (default)
        await pilot.pause()
        await pilot.pause()

        assert recorder.calls == [["docker", "system", "prune", "-af"]]


async def test_docker_prune_with_volumes_confirmed(monkeypatch, fake_trash):
    recorder = _patch_docker_sims(monkeypatch, docker=_docker_dict())
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()

        await pilot.press("D")
        await pilot.pause()
        for ch in "yes":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.click("#confirm")  # confirm volumes too
        await pilot.pause()
        await pilot.pause()

        assert recorder.calls == [["docker", "system", "prune", "-af", "--volumes"]]


async def test_simulators_delete_unavailable_confirmed(monkeypatch, fake_trash):
    recorder = _patch_docker_sims(monkeypatch, sims=[_sim()])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()

        await pilot.press("S")
        await pilot.pause()
        for ch in "yes":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assert recorder.calls == [["xcrun", "simctl", "delete", "unavailable"]]


async def test_docker_and_sims_absent_no_sections_notify_only(monkeypatch, fake_trash):
    recorder = _patch_docker_sims(monkeypatch, docker=None, sims=[])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()

        assert list(host.screen.query_one("#docker-section").children) == []
        assert list(host.screen.query_one("#sims-section").children) == []
        try:
            host.screen.query_one("#docker", Static)
            assert False, "docker Static should not be mounted"
        except NoMatches:
            pass
        try:
            host.screen.query_one("#sims", Static)
            assert False, "sims Static should not be mounted"
        except NoMatches:
            pass

        await pilot.press("D")
        await pilot.pause()
        await pilot.press("S")
        await pilot.pause()

        assert recorder.calls == []


async def test_resume_during_slow_trash_does_not_rescan(tmp_path, monkeypatch, fake_trash):
    """Rider mirroring space_finder's test_resume_during_slow_trash_does_not_rescan
    on the artifacts zone: _trashing must span ConfirmModal -> trash worker so a
    resume mid-flight (navigate away, come back) doesn't fire a rescan that
    races _refresh_list()."""
    f = tmp_path / "node_modules"
    f.mkdir()
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts", lambda: [_row(f)])
    monkeypatch.setattr("ui.screens.dev_junk.find_docker_junk", lambda: None)
    monkeypatch.setattr("ui.screens.dev_junk.find_simulators", lambda: [])

    rescan_calls = []
    real_rescan = dev_junk_mod.DevJunkScreen._rescan

    def counting_rescan(self):
        rescan_calls.append(1)
        real_rescan(self)

    monkeypatch.setattr(dev_junk_mod.DevJunkScreen, "_rescan", counting_rescan)

    real_safe_delete = dev_junk_mod.safe_delete

    def slow_safe_delete(*args, **kwargs):
        time.sleep(0.3)
        return real_safe_delete(*args, **kwargs)

    monkeypatch.setattr("ui.screens.dev_junk.safe_delete", slow_safe_delete)

    class NavHost(App):
        SCREENS = {"dev_junk": DevJunkScreen}
        BINDINGS = [("1", "push_screen('dev_junk')", "Dev Junk")]

    app = NavHost()
    async with app.run_test() as pilot:
        await pilot.press("1")
        await pilot.pause()                  # initial mount -> _rescan call #1
        sel = app.screen.query_one("#list-artifacts", SelectionList)
        sel.focus()
        await pilot.press("space")
        await pilot.press("t")
        await pilot.pause()
        await pilot.click("#confirm")        # starts the 0.3s-slow trash worker
        await pilot.press("escape")          # navigate away mid-flight
        await pilot.pause()
        await pilot.press("1")               # re-enter mid-flight - must NOT rescan
        await pilot.pause()
        await asyncio.sleep(0.4)             # let the slow worker land
        await pilot.pause()
        await pilot.pause()
        # something was trashed, so the reclaim gate is now on top of the
        # stack - the DevJunkScreen itself lives one level down
        dj_screen = app.screen_stack[-2]
        assert dj_screen.query_one("#list-artifacts", SelectionList).option_count == 0
        await pilot.press("escape")          # decline the reclaim gate

    assert rescan_calls == [1]                # only the initial on_mount rescan
    assert not f.exists()
    assert (fake_trash / "node_modules").exists()
