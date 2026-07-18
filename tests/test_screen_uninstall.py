from textual.app import App

from core.deleter import DeleteReport
from ui.screens.uninstall import UninstallScreen


class Host(App):
    def on_mount(self):
        self.push_screen(UninstallScreen())


async def test_uninstall_flow_confirm(monkeypatch, fake_trash):
    monkeypatch.setattr("ui.screens.uninstall.get_installed_apps",
                        lambda: [{"name": "TestApp", "path": "/Applications/TestApp.app",
                                  "size": 1000}])
    calls = []

    def fake_uninstall(name, dry_run=False):
        calls.append((name, dry_run))
        return {"app": DeleteReport("app_bundle", dry_run=dry_run),
                "leftovers": DeleteReport("app_leftovers", dry_run=dry_run)}

    monkeypatch.setattr("ui.screens.uninstall.uninstall_app", fake_uninstall)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")     # select the row -> ConfirmModal
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()
    assert calls == [("TestApp", False)]


async def test_uninstall_decline_does_nothing(monkeypatch):
    monkeypatch.setattr("ui.screens.uninstall.get_installed_apps",
                        lambda: [{"name": "TestApp", "path": "/x", "size": 1}])
    calls = []
    monkeypatch.setattr("ui.screens.uninstall.uninstall_app",
                        lambda *a, **k: calls.append(1))
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert calls == []
