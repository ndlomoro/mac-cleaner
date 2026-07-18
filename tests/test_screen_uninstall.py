from textual.app import App

from core.deleter import DeleteReport, Outcome, PathResult
from ui.screens.uninstall import UninstallScreen


class Host(App):
    def on_mount(self):
        self.push_screen(UninstallScreen())


def _fake_uninstall_factory(calls):
    def fake_uninstall(name, dry_run=False):
        calls.append((name, dry_run))
        app_report = DeleteReport("app_bundle", dry_run=dry_run)
        app_report.results.append(
            PathResult(f"/Applications/{name}.app", Outcome.TRASHED, 1000))
        leftovers_report = DeleteReport("app_leftovers", dry_run=dry_run)
        return {"app": app_report, "leftovers": leftovers_report}
    return fake_uninstall


async def test_row_select_triggers_dry_run_and_shows_preview(monkeypatch, fake_trash):
    monkeypatch.setattr("ui.screens.uninstall.get_installed_apps",
                        lambda: [{"name": "TestApp", "path": "/Applications/TestApp.app",
                                  "size": 1000}])
    calls = []
    monkeypatch.setattr("ui.screens.uninstall.uninstall_app", _fake_uninstall_factory(calls))
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")     # select the row -> dry-run + preview
        await pilot.pause()
        assert calls == [("TestApp", True)]
        # ConfirmModal is now on top of the stack; the preview lives on the
        # UninstallScreen underneath it and must already be rendered.
        uninstall_screen = host.screen_stack[-2]
        text = str(uninstall_screen.query_one("#preview").content)
        assert "/Applications/TestApp.app" in text


async def test_uninstall_flow_confirm(monkeypatch, fake_trash):
    monkeypatch.setattr("ui.screens.uninstall.get_installed_apps",
                        lambda: [{"name": "TestApp", "path": "/Applications/TestApp.app",
                                  "size": 1000}])
    calls = []
    monkeypatch.setattr("ui.screens.uninstall.uninstall_app", _fake_uninstall_factory(calls))
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")     # select the row -> dry-run + preview
        await pilot.pause()
        await pilot.click("#confirm")  # ConfirmModal is mounted after the preview
        await pilot.pause()
    assert calls == [("TestApp", True), ("TestApp", False)]


async def test_uninstall_decline_does_nothing(monkeypatch, fake_trash):
    monkeypatch.setattr("ui.screens.uninstall.get_installed_apps",
                        lambda: [{"name": "TestApp", "path": "/Applications/TestApp.app",
                                  "size": 1000}])
    calls = []
    monkeypatch.setattr("ui.screens.uninstall.uninstall_app", _fake_uninstall_factory(calls))
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")   # decline the ConfirmModal
        await pilot.pause()
    assert calls == [("TestApp", True)]   # only the dry-run happened


async def test_uninstall_value_error_notifies_with_error_severity(monkeypatch):
    monkeypatch.setattr("ui.screens.uninstall.get_installed_apps",
                        lambda: [{"name": "Bad", "path": "/Applications/Bad.app",
                                  "size": 1}])

    def boom(name, dry_run=False):
        raise ValueError("invalid app name")

    monkeypatch.setattr("ui.screens.uninstall.uninstall_app", boom)
    notifications = []
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        host.screen.notify = lambda msg, **kw: notifications.append((msg, kw.get("severity")))
        await pilot.press("enter")
        await pilot.pause()
    assert notifications
    assert notifications[-1][1] == "error"
