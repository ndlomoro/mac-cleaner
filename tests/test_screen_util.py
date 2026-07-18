"""Unit coverage for the screen-resume-rescan plumbing in ui/screens/_util.py -
independent of any specific screen, since the depth-counter guarantee (a
sequential chain of modals separated by async work must suppress exactly its
own resumes, no more, no less) is a property of the helpers themselves."""
import asyncio
import time

from textual.app import App
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Static

from ui.screens._util import push_modal, run_offthread, skip_resume_rescan


class _Modal(ModalScreen[bool]):
    def compose(self):
        yield Button("ok", id="ok")

    def on_button_pressed(self, event) -> None:
        self.dismiss(True)


class _ChainScreen(Screen):
    def compose(self):
        yield Static("hi")

    def on_mount(self) -> None:
        self.rescans = 0

    def _rescan(self) -> None:
        self.rescans += 1

    def on_screen_resume(self) -> None:
        if skip_resume_rescan(self):
            return
        self._rescan()

    def start_chain(self) -> None:
        # Mirrors Task 7's TypedGate -> (async work) -> Confirm shape: a
        # second modal is pushed only after the first dismisses AND an
        # off-thread step in between completes - never simultaneously
        # stacked, always sequential.
        def _after_first(confirmed: bool | None) -> None:
            def _work() -> bool:
                time.sleep(0.05)
                return True

            def _done(_result) -> None:
                push_modal(self, _Modal(), lambda _c: None)

            def _error(_exc) -> None:
                pass

            run_offthread(self, _work, _done, _error)

        push_modal(self, _Modal(), _after_first)


class _Host(App):
    def on_mount(self) -> None:
        self.push_screen(_ChainScreen())


async def test_chained_modals_suppress_exactly_their_own_resumes():
    host = _Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        screen = host.screen
        assert screen.rescans == 0            # mount-adjacent resume skipped

        screen.start_chain()
        await pilot.pause()
        await pilot.click("#ok")              # dismiss modal #1 -> resume #1
        await pilot.pause()
        await asyncio.sleep(0.15)             # worker lands, pushes modal #2
        await pilot.pause()
        await pilot.click("#ok")              # dismiss modal #2 -> resume #2
        await pilot.pause()
        assert screen.rescans == 0             # neither chained resume rescanned

        # the NEXT genuine re-entry (no modal involved this time) must still
        # rescan normally - the depth counter must not get stuck suppressing.
        host.push_screen(_ChainScreen())
        await pilot.pause()
        host.pop_screen()
        await pilot.pause()
        assert screen.rescans == 1
