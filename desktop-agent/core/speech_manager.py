from __future__ import annotations

from PySide6.QtCore import QObject

from core.conversation_state import ConversationStateMachine
from core.voice import SpeechSpeaker


class SpeechManager(QObject):
    """
    Originally fixed a real crash: ChatPanel used to hold a single
    `self._speaker` reference and reassign it on every call to _speak().
    If a second _speak() happened while the first SpeechSpeaker's QThread
    was still running pyttsx3's runAndWait(), the reassignment dropped
    the only Python reference to the still-running thread, and Qt
    destroyed a running QThread: "QThread: Destroyed while thread is
    still running", process dead. The queue below (only one SpeechSpeaker
    ever alive at a time) fixes *that* failure mode.

    THAT FIX WAS INCOMPLETE. The queue guard stops a *second* speak()
    from overwriting `self._current`, but `_on_finished` -- the only
    place that ever clears `self._current` -- used to drop the reference
    as soon as the custom `finished_speaking` signal arrived, not after
    confirming the OS thread had actually ended. `finished_speaking` is
    emitted from the *last line inside* SpeechSpeaker.run(), which is
    strictly before Qt's own thread-finalization runs (the code that
    actually flips isRunning() to False and lets the OS thread exit).
    Because that signal is a queued cross-thread connection, delivery to
    this slot depends entirely on when the main thread's event loop gets
    around to it -- there is no guarantee it happens after the worker
    thread has fully unwound, only that it happens after emit() posts
    the event. Under GIL contention from other threads doing real work
    at the same time (exactly the situation at startup: SpeakerSyncWorker,
    VoiceListener, the WebSocket thread, and the first health-check/
    reminder-poll workers are all alive within milliseconds of each
    other), the worker thread can be descheduled for the few remaining
    bytecodes between "signal posted" and "run() actually returns", and
    the main thread can process the already-queued event before that
    happens. Reproduced directly: a faithful port of this exact
    queue-guarded logic, driven by a QTimer under simulated GIL
    contention from a handful of busy threads, hits "QThread: Destroyed
    while thread is still running" / exit 134 on every run; switching
    `_on_finished` to `wait()` before clearing the reference (below)
    eliminates it across repeated runs of the same harness.

    The fix: `_on_finished` now calls `self._current.wait()` -- a real
    OS-level join -- before clearing the reference. `wait()` is the only
    authoritative source for "has the native thread actually finished";
    a signal emitted from inside run() is not. By the time this slot
    runs, the thread is at most a few instructions from done, so this
    essentially never blocks in practice, but it makes the drop provably
    safe instead of racy.
    """

    def __init__(self, fsm: ConversationStateMachine):
        super().__init__()
        self._fsm = fsm
        self._queue: list[str] = []
        self._current: SpeechSpeaker | None = None

    def speak(self, text: str) -> None:
        if not text:
            if self._current is None:
                self._fsm.on_response_complete()  # nothing queued or speaking -- don't leave the FSM stuck
            return
        self._queue.append(text)
        self._maybe_start_next()

    def _maybe_start_next(self) -> None:
        if self._current is not None or not self._queue:
            return
        text = self._queue.pop(0)
        self._current = SpeechSpeaker(text, self._fsm)
        self._current.finished_speaking.connect(self._on_finished)
        self._current.start()

    def _on_finished(self) -> None:
        # See class docstring: `finished_speaking` fires before the OS
        # thread has necessarily finished unwinding. wait() with no
        # timeout blocks until it genuinely has -- by this point that's
        # at most a few instructions away, never a real stall.
        if self._current is not None:
            self._current.wait()
        self._current = None
        self._maybe_start_next()

    def shutdown(self, timeout_ms: int = 2000) -> None:
        """Called from app shutdown -- waits for the in-flight speaker
        rather than letting the app quit out from under it (same failure
        mode as the bug above, just triggered by process exit instead of
        a second _speak() call)."""
        self._queue.clear()
        if self._current is not None:
            self._current.wait(timeout_ms)
