"""Shared worker helper - runs blocking work off-thread, exception-safe."""
from typing import Any, Callable

from textual.screen import Screen


def run_offthread(
    screen: Screen,
    work: Callable[[], Any],
    done: Callable[[Any], None],
    on_error: Callable[[Exception], None],
) -> None:
    """Run work() in a thread worker; marshal done(result) or on_error(exc)
    back to the UI thread. Exactly one of the two callbacks always fires."""

    def _runner() -> None:
        try:
            result = work()
        except Exception as e:  # noqa: BLE001 - boundary: nothing may escape a worker silently
            screen.app.call_from_thread(on_error, e)
            return
        screen.app.call_from_thread(done, result)

    screen.run_worker(_runner, thread=True)
