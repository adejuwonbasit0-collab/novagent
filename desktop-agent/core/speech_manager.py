from __future__ import annotations

from PySide6.QtCore import QObject

from core.conversation_state import ConversationStateMachine
from core.voice import SpeechSpeaker


class SpeechManager(QObject):
    """
    Fixes a real crash: ChatPanel used to hold a single `self._speaker`
    reference and reassign it on every call to _speak(). If a second
    _speak() happened while the first SpeechSpeaker's QThread was still
    running pyttsx3's runAndWait() -- which is exactly what happens when
    "I'm listening for Nova" is still being spoken and a microphone
    init error fires _on_voice_error() a moment later -- the reassignment
    dropped the only Python reference to the still-running thread. Qt
    then destroys a running QThread and calls abort(): "QThread:
    Destroyed while thread is still running" followed by the process
    dying immediately. Reproduced directly (exit code 134, identical
    stderr) against a minimal repro before writing this fix.

    This queues instead of overwriting: only one SpeechSpeaker is ever
    alive at a time, and it's never dropped until its own
    finished_speaking signal confirms the OS thread has actually ended.
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
