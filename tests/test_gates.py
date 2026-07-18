from textual.app import App
from textual.widgets import Button

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


async def test_confirm_modal_cancel_button():
    host = Host(ConfirmModal("Move 1 item to Trash?"))
    async with host.run_test() as pilot:
        await pilot.click("#cancel")
    assert host.result is False


async def test_typed_gate_cancel_button():
    host = Host(TypedGateModal("Delete"))
    async with host.run_test() as pilot:
        await pilot.click("#cancel")
    assert host.result is False


async def test_confirm_modal_custom_confirm_label():
    # Default preserved for every existing call site (trashing).
    host = Host(ConfirmModal("Move 1 item to Trash?"))
    async with host.run_test() as pilot:
        assert host.screen.query_one("#confirm", Button).label == "Move to Trash"
        await pilot.press("escape")

    # A permanent, non-Trash action (e.g. Docker volume pruning) must not
    # show the dishonest "Move to Trash" label on its confirm button.
    host = Host(ConfirmModal("Also prune volumes?", confirm_label="Prune volumes"))
    async with host.run_test() as pilot:
        assert host.screen.query_one("#confirm", Button).label == "Prune volumes"
        await pilot.click("#confirm")
    assert host.result is True


async def test_confirm_modal_custom_decline_label():
    # Default preserved for every existing call site.
    host = Host(ConfirmModal("Move 1 item to Trash?"))
    async with host.run_test() as pilot:
        assert host.screen.query_one("#cancel", Button).label == "Cancel"
        await pilot.press("escape")

    # The volumes prompt's decline branch means "images only, no volumes" -
    # a plain "Cancel" would falsely imply nothing happens at all.
    host = Host(ConfirmModal("Also prune volumes?", confirm_label="Prune volumes",
                             decline_label="Images only"))
    async with host.run_test() as pilot:
        assert host.screen.query_one("#cancel", Button).label == "Images only"
        await pilot.click("#cancel")
    assert host.result is False
