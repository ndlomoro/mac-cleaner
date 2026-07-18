from textual.app import App

from ui.widgets.gates import ConfirmModal, TypedGateModal


class Host(App):
    def __init__(self, modal):
        super().__init__()
        self._modal = modal
        self.result: bool | None = None

    def on_mount(self) -> None:
        self.push_screen(self._modal, lambda v: setattr(self, "result", v))


async def test_confirm_modal_confirm_and_cancel():
    host = Host(ConfirmModal("Move 3 items (~1.2 GB) to Trash?"))
    async with host.run_test() as pilot:
        await pilot.click("#confirm")
    assert host.result is True

    host = Host(ConfirmModal("Move 3 items to Trash?"))
    async with host.run_test() as pilot:
        await pilot.press("escape")
    assert host.result is False


async def test_typed_gate_requires_literal_yes():
    host = Host(TypedGateModal("Delete 2 snapshots"))
    async with host.run_test() as pilot:
        await pilot.click("#gate-input")
        await pilot.press(*"sure", "enter")
    assert host.result is False

    host = Host(TypedGateModal("Delete 2 snapshots"))
    async with host.run_test() as pilot:
        await pilot.click("#gate-input")
        await pilot.press(*"YES", "enter")
    assert host.result is True


async def test_typed_gate_escape_rejects():
    host = Host(TypedGateModal("Delete"))
    async with host.run_test() as pilot:
        await pilot.press("escape")
    assert host.result is False
