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


def run_gated(
    screen: Screen,
    busy_attr: str,
    work: Callable[[], Any],
    done: Callable[[Any], None],
    on_error: Callable[[Exception], None],
) -> None:
    """Like run_offthread, but also owns the terminal edge of a busy flag.

    Sets `getattr(screen, busy_attr)` True before starting work, and clears
    it (in a finally, so it clears even if done()/on_error() itself raises)
    right after whichever of done/on_error runs. Use this for the LAST async
    step of a destructive flow (the one whose completion truly ends the
    busy span) - a step whose `done` callback conditionally chains into
    another gate/worker (e.g. Junk's clean -> offer-reclaim) must NOT use
    this, since the flag would be cleared the instant `done()` returns, before
    the chained step's own terminal callback fires. For those, set the busy
    flag manually at the action's entry point (before the first modal is
    pushed) and clear it explicitly in every branch that actually ends the
    flow (a decline branch, an error branch, or - for the branch that chains
    further - not at all, leaving it to the next step's run_gated/manual
    clear).
    """
    setattr(screen, busy_attr, True)

    def _done(result: Any) -> None:
        try:
            done(result)
        finally:
            setattr(screen, busy_attr, False)

    def _error(exc: Exception) -> None:
        try:
            on_error(exc)
        finally:
            setattr(screen, busy_attr, False)

    run_offthread(screen, work, _done, _error)


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

    The modal-suppression side is a depth counter, not a boolean: a screen
    can chain a second push_modal off the first modal's callback with async
    work in between (TypedGate -> worker -> Confirm), and each push_modal
    call increments the count independently of when its resume actually
    fires. A boolean set/cleared per-call is not safe here - if a second
    push_modal lands before the first modal's resume is delivered, a
    boolean would already be consumed and the second dismissal's resume
    would incorrectly fall through to a real rescan. The counter has no
    such ordering dependency: N pushes still consume exactly N resumes,
    whatever order dismissals and worker callbacks interleave in.
    """
    if is_initial_resume(screen):
        return True
    depth = getattr(screen, "_suppress_resume_depth", 0)
    if depth > 0:
        screen._suppress_resume_depth = depth - 1
        return True
    return False


def push_modal(screen: Screen, modal: ModalScreen, callback=None) -> None:
    """Push a gate/confirm modal on top of `screen` without it being
    mistaken for a real return-to-screen navigation.

    Textual fires Screen.on_screen_resume on `screen` when `modal` is later
    dismissed - the exact same signal a genuine "user navigated back to this
    screen" resume produces. Screens that push modals mid-flow (confirm/gate
    dialogs after Clean, Trash, Uninstall, etc.) must route every push
    through here instead of calling screen.app.push_screen(modal, callback)
    directly, or the modal's dismissal will trigger an unwanted rescan that
    clobbers state the in-flight action just finished writing (e.g. a
    just-trashed item reappearing because the stale mocked/real scan
    re-adds it). Chained modals (push_modal called again from within an
    earlier modal's callback) each increment the same counter - see
    skip_resume_rescan for why this must be a counter and not a flag.
    """
    screen._suppress_resume_depth = getattr(screen, "_suppress_resume_depth", 0) + 1
    screen.app.push_screen(modal, callback)
