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


def _no_docker_or_sims(monkeypatch):
    """Tests exercising only the artifacts zone must not shell out to the
    REAL docker/xcrun via find_docker_junk/find_simulators - besides being
    slow/non-deterministic across machines, letting the real scan run long
    enough can leave _scanning True past a single pilot.pause(), which the
    trash/prune/sim actions now correctly treat as busy and refuse."""
    monkeypatch.setattr("ui.screens.dev_junk.find_docker_junk", lambda: None)
    monkeypatch.setattr("ui.screens.dev_junk.find_simulators", lambda: [])


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
    _no_docker_or_sims(monkeypatch)
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
    _no_docker_or_sims(monkeypatch)
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
    _no_docker_or_sims(monkeypatch)
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
    _no_docker_or_sims(monkeypatch)
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
    # hard-protected -> SKIPPED. A nonexistent name under ~/.ssh, not the
    # developer's real key: is_protected() runs before any existence check,
    # so the protection assertion still holds without risking the real
    # ~/.ssh/id_ed25519 if this protection ever regresses (the trash fake
    # in some fixtures renames the path it's given).
    hard = P.home() / ".ssh" / "mac-cleaner-test-nonexistent-key"
    rows = [_row(good), _row(hard, size=5, age_days=900, kind="venv", project="ssh")]
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts", lambda: rows)
    _no_docker_or_sims(monkeypatch)
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
    _no_docker_or_sims(monkeypatch)
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


async def test_row_label_shows_abbreviated_path(tmp_path, monkeypatch, fake_trash):
    long_path = tmp_path / ("a" * 60) / "node_modules"
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts",
                        lambda: [_row(long_path)])
    _no_docker_or_sims(monkeypatch)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        sel = host.screen.query_one("#list-artifacts", SelectionList)
        label = str(sel.get_option_at_index(0).prompt)
        full = str(long_path)
        assert full not in label            # too long -> abbreviated
        assert f"…{full[-40:]}" in label


async def test_row_label_shows_full_path_when_short(monkeypatch, fake_trash):
    short_path = "/tmp/proj/node_modules"   # deliberately short/fixed, unlike
    # tmp_path (macOS temp dirs are themselves 40+ chars, which would
    # spuriously abbreviate and defeat this "short path" case)
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts",
                        lambda: [_row(short_path)])
    _no_docker_or_sims(monkeypatch)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        sel = host.screen.query_one("#list-artifacts", SelectionList)
        label = str(sel.get_option_at_index(0).prompt)
        assert str(short_path) in label


async def test_cache_root_row_renders_no_fake_staleness(tmp_path, monkeypatch, fake_trash):
    row = _row(tmp_path / "caches", age_days=None, kind="gradle_cache",
               project="gradle cache")
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts", lambda: [row])
    _no_docker_or_sims(monkeypatch)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        sel = host.screen.query_one("#list-artifacts", SelectionList)
        label = str(sel.get_option_at_index(0).prompt)
        assert "d idle" not in label
        assert "—" in label


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


async def test_shared_refresh_counter_prevents_resume_rescan_race(monkeypatch, fake_trash):
    """Reviewer repro: _rescan_docker/_rescan_sims used to share a single
    _scanning boolean. A fast sims refresh landing while a slow docker
    refresh is still in flight cleared that boolean out from under the
    docker refresh, so a resume mid-window incorrectly fired a full
    _rescan() (clobbering whatever _fill_docker/_fill_sims were writing -
    the DuplicateIds crash the review flagged is one symptom of this race).
    The _refreshing counter must stay > 0 as long as EITHER refresh is
    outstanding, regardless of which one finishes first."""
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts", lambda: [])

    def slow_docker():
        time.sleep(0.3)
        return _docker_dict()

    def fast_sims():
        return [_sim()]

    monkeypatch.setattr("ui.screens.dev_junk.find_docker_junk", slow_docker)
    monkeypatch.setattr("ui.screens.dev_junk.find_simulators", fast_sims)

    rescan_calls = []
    real_rescan = dev_junk_mod.DevJunkScreen._rescan

    def counting_rescan(self):
        rescan_calls.append(1)
        real_rescan(self)

    monkeypatch.setattr(dev_junk_mod.DevJunkScreen, "_rescan", counting_rescan)

    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await asyncio.sleep(0.4)   # let the initial on_mount scan fully settle
        await pilot.pause()
        assert rescan_calls == [1]

        # Mirrors what the D/S bindings do after a prune/delete: kick off a
        # fast sims-only refresh and a slow docker-only refresh together.
        host.screen._rescan_sims()
        host.screen._rescan_docker()
        await pilot.pause()             # let the fast sims refresh land and decrement
        host.screen.on_screen_resume()  # docker refresh still in flight - must be a no-op
        await pilot.pause()
        await asyncio.sleep(0.4)        # let the slow docker refresh land
        await pilot.pause()

    assert rescan_calls == [1]          # still only the initial mount rescan


async def test_docker_prune_rc_nonzero_reports_error_not_reclaimed(monkeypatch, fake_trash):
    # Reviewer repro: run_command's rc was silently ignored, so a daemon
    # that fails to prune (e.g. "docker" not running) was reported to the
    # user as a success ("Reclaimed: ...").
    _patch_docker_sims(monkeypatch, docker=_docker_dict())
    monkeypatch.setattr("ui.screens.dev_junk.run_command",
                        lambda argv, sudo=False: ("", "daemon not running", 1))
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        notifications = []
        host.screen.notify = lambda msg, **kw: notifications.append(
            (msg, kw.get("severity")))

        await pilot.press("D")
        await pilot.pause()
        for ch in "yes":
            await pilot.press(ch)
        await pilot.press("enter")     # TypedGateModal confirmed -> volumes ConfirmModal
        await pilot.pause()
        await pilot.press("escape")    # decline volumes
        await pilot.pause()
        await pilot.pause()

        assert not any("Reclaimed" in msg for msg, _ in notifications)
        errors = [msg for msg, sev in notifications if sev == "error"]
        assert any("Docker prune failed" in msg and "daemon not running" in msg
                   for msg in errors)


async def test_simulator_cleanup_rc_nonzero_reports_error_not_deleted(monkeypatch, fake_trash):
    _patch_docker_sims(monkeypatch, sims=[_sim()])
    monkeypatch.setattr("ui.screens.dev_junk.run_command",
                        lambda argv, sudo=False: ("", "daemon not running", 1))
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        notifications = []
        host.screen.notify = lambda msg, **kw: notifications.append(
            (msg, kw.get("severity")))

        await pilot.press("S")
        await pilot.pause()
        for ch in "yes":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        assert not any("Deleted" in msg for msg, _ in notifications)
        errors = [msg for msg, sev in notifications if sev == "error"]
        assert any("Simulator cleanup failed" in msg and "daemon not running" in msg
                   for msg in errors)


def _sync_run_offthread(screen, work, done, on_error):
    """Test stand-in for run_offthread that runs synchronously (no real
    thread worker) so a raise out of `done` can be observed directly instead
    of surfacing as an opaque textual.worker.WorkerFailed at app teardown -
    run_offthread itself never guards a `done` raise (see its docstring), so
    this mirrors production behavior; it just lets the test catch what
    production would otherwise propagate."""
    result = work()
    try:
        done(result)
    except Exception:
        pass


async def test_rescan_docker_refreshing_counter_does_not_leak_on_fill_error(
        monkeypatch, fake_trash):
    # Reviewer repro: if _fill_docker/_fill_sims raises, the decrement was
    # skipped and _refreshing stayed > 0 forever, wedging _busy() permanently.
    _patch_docker_sims(monkeypatch, docker=_docker_dict())
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()

        def _boom(_docker):
            raise RuntimeError("boom")

        monkeypatch.setattr(host.screen, "_fill_docker", _boom)
        monkeypatch.setattr("ui.screens.dev_junk.run_offthread", _sync_run_offthread)
        host.screen._rescan_docker()
        await pilot.pause()

        assert host.screen._refreshing == 0
        assert not host.screen._busy()


async def test_rescan_sims_refreshing_counter_does_not_leak_on_fill_error(
        monkeypatch, fake_trash):
    _patch_docker_sims(monkeypatch, sims=[_sim()])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()

        def _boom(_sims):
            raise RuntimeError("boom")

        monkeypatch.setattr(host.screen, "_fill_sims", _boom)
        monkeypatch.setattr("ui.screens.dev_junk.run_offthread", _sync_run_offthread)
        host.screen._rescan_sims()
        await pilot.pause()

        assert host.screen._refreshing == 0
        assert not host.screen._busy()


async def test_docker_prune_refused_while_trashing(tmp_path, monkeypatch, fake_trash):
    """Cross-guard: the three action flows (t/D/S) share one screen's worth
    of busy state - a Docker prune must be refused while a trash is still
    in flight, not just while another prune is in flight."""
    f = tmp_path / "node_modules"
    f.mkdir()
    monkeypatch.setattr("ui.screens.dev_junk.find_project_artifacts", lambda: [_row(f)])
    monkeypatch.setattr("ui.screens.dev_junk.find_docker_junk", lambda: _docker_dict())
    monkeypatch.setattr("ui.screens.dev_junk.find_simulators", lambda: [])
    recorder = _RunCommandRecorder()
    monkeypatch.setattr("ui.screens.dev_junk.run_command", recorder)

    real_safe_delete = dev_junk_mod.safe_delete

    def slow_safe_delete(*args, **kwargs):
        time.sleep(0.3)
        return real_safe_delete(*args, **kwargs)

    monkeypatch.setattr("ui.screens.dev_junk.safe_delete", slow_safe_delete)

    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        sel = host.screen.query_one("#list-artifacts", SelectionList)
        sel.focus()
        await pilot.press("space")
        await pilot.press("t")
        await pilot.pause()
        await pilot.click("#confirm")   # starts the 0.3s-slow trash worker
        await pilot.press("D")          # refused: a trash is in flight
        await pilot.pause()
        assert recorder.calls == []

        await asyncio.sleep(0.4)        # let the slow trash worker land
        await pilot.pause()
        await pilot.press("escape")     # decline the reclaim offer

    assert not f.exists()
    assert (fake_trash / "node_modules").exists()
