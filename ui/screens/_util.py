"""Shared worker helper - runs blocking work off-thread, exception-safe."""
from typing import Any, Callable

from textual.screen import ModalScreen, Screen


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


def is_initial_resume(screen: Screen) -> bool:
    """Guard for the screen-resume-rescan convention.

    Textual (verified empirically on 8.2.8) fires Screen.on_screen_resume
    once immediately after the very first on_mount - before any real
    re-entry to the screen - both for screens installed by class via
    App.SCREENS and for screens pushed as bare instances. Since on_mount has
    already started the initial scan by the time that first resume fires,
    on_screen_resume must not rescan on that call or every screen would
    scan twice on first entry.

    Call this at the top of on_screen_resume: the first call (the mount-
    adjacent one) returns True and the caller should skip rescanning; every
    call after that returns False, meaning it's a genuine return-to-screen
    resume and the caller should rescan (subject to its own busy guard).
    """
    first = not getattr(screen, "_resumed_once", False)
    screen._resumed_once = True
    return first


def skip_resume_rescan(screen: Screen) -> bool:
    """True if on_screen_resume should return without rescanning.

    Combines the two non-navigation reasons a resume can fire: the mount-
    adjacent first resume (see is_initial_resume) and a modal this screen
    itself pushed (see push_modal) being dismissed. Callers still need their
    own busy-flag check on top of this for the case where a real re-entry
    lands mid in-flight scan/action.
    """
    if is_initial_resume(screen):
        return True
    if getattr(screen, "_suppress_next_resume", False):
        screen._suppress_next_resume = False
        return True
    return False


def push_modal(screen: Screen, modal: ModalScreen, callback=None) -> None:
    """Push a gate/confirm modal on top of `screen` without it being
    mistaken for a real return-to-screen navigation.

    Textual fires Screen.on_screen_resume on `screen` when `modal` is later
    dismissed - the exact same signal a genuine "user navigated back to this
    screen" resume produces. Screens that push modals mid-flow (confirm/gate
    dialogs after Clean, Trash, Uninstall, etc.) must route the push through
    here instead of calling screen.app.push_screen(modal, callback) directly,
    or the modal's dismissal will trigger an unwanted rescan that clobbers
    state the in-flight action just finished writing (e.g. a just-trashed
    item reappearing because the stale mocked/real scan re-adds it).
    """
    screen._suppress_next_resume = True
    screen.app.push_screen(modal, callback)
