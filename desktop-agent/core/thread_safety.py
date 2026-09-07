from __future__ import annotations

"""
Thread ownership rule (enforced here, not just documented): a QThread's
Python reference is NEVER dropped, reassigned, or allowed to fall out of
scope while Qt still considers it running. The only two safe ways to know
a QThread has actually finished are (a) `thread.wait(timeout)` returning
True, or (b) the thread's own `finished` signal having fired. Guessing a
timeout and proceeding anyway -- which is exactly what caused
"QThread: Destroyed while thread is still running" every time this bug
resurfaced in this codebase -- is never acceptable, however generous the
timeout looks.

Use `stop_and_release(thread, stop_fn, timeout_ms, on_released)` for every
QThread this app ever stops. It is the single place this logic lives, so
fixing it once fixes it everywhere, and any new call site gets the correct
behavior automatically instead of a hand-rolled (and easy to get wrong)
wait()+null pattern.
"""

import logging
import threading
import time

from PySide6.QtCore import QThread

logger = logging.getLogger("nova.threads")


def log_thread_event(event: str, thread: QThread) -> None:
    """
    Diagnostic logging requested explicitly for tracing thread lifecycle
    issues: object identity, class name, and Qt's own isRunning/isFinished
    state at the moment of the event. Cheap enough to leave on permanently
    -- this is exactly the data needed to identify which thread is
    responsible if a "QThread: Destroyed while thread is still running"
    error is ever seen again, rather than having to add print statements
    and reproduce it a second time.
    """
    logger.info(
        "[THREAD] %s id=0x%x name=%s os_thread=%s isRunning=%s isFinished=%s",
        event,
        id(thread),
        type(thread).__name__,
        threading.current_thread().name,
        thread.isRunning(),
        thread.isFinished(),
    )


def stop_and_release(
    thread: QThread | None,
    stop_fn,
    timeout_ms: int,
    on_released,
) -> None:
    """
    The one correct way to stop a QThread and release its reference.

    thread:      the QThread to stop, or None (no-op).
    stop_fn:     called first to ask the thread to end (e.g. sets a flag
                 the run() loop checks, or calls sd.stop() to abort a
                 blocking call). Must not block.
    timeout_ms:  how long to wait for a clean stop before giving up on
                 waiting synchronously.
    on_released: called with no arguments exactly once, either
                 immediately (if the thread finished within timeout_ms)
                 or later, from the thread's own `finished` signal --
                 NEVER called while thread.isRunning() could still be
                 True. This is what the caller uses to actually null out
                 its reference; stop_and_release never touches the
                 caller's attribute itself, so there's no way to
                 accidentally null it early from here either.
    """
    if thread is None:
        on_released()
        return

    log_thread_event("STOP_REQUESTED", thread)
    stop_fn()

    if thread.wait(timeout_ms):
        log_thread_event("STOPPED_CLEANLY", thread)
        on_released()
        return

    # Did not finish within the timeout. Do NOT proceed as if it had --
    # that guess is exactly what caused this bug every previous time.
    # Defer the release to the thread's own `finished` signal, which Qt
    # guarantees fires only after the native thread has actually ended.
    logger.warning(
        "[THREAD] TIMEOUT waiting for %s (id=0x%x) to stop after %dms -- "
        "deferring release to its finished signal instead of proceeding",
        type(thread).__name__,
        id(thread),
        timeout_ms,
    )

    def _on_finished():
        log_thread_event("STOPPED_AFTER_TIMEOUT", thread)
        on_released()

    thread.finished.connect(_on_finished)
