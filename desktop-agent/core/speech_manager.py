from __future__ import annotations

"""
A SINGLE, long-lived TTS worker thread for the entire app lifetime,
created once and never recreated -- per explicit direction: "There must
never be multiple uncontrolled pyttsx3 engines running simultaneously...
Prefer a SINGLE long-lived speech worker/engine... rather than repeatedly
creating and destroying pyttsx3 QThreads."

Earlier version of this file (still queued correctly, but spun up a brand
new SpeechSpeaker QThread per utterance) was a real fix for the specific
crash it targeted -- but "repeatedly create and destroy QThreads" is
itself a pattern that keeps re-opening the same class of bug on any call
site that isn't perfectly careful (see core/thread_safety.py's docstring
for the history of that happening three separate times in this codebase).
A single persistent worker removes the whole category: there is exactly
one QThread for TTS, created at startup and stopped at shutdown, and
"speaking" is just pushing text onto a queue that worker consumes --  no
QThread is ever created, reassigned, or destroyed mid-speech.

Lifecycle (matches the requested CREATED -> STARTED -> PROCESSING ->
FINISHED -> STOPPED -> DESTROYED):
  CREATED   -- SpeechWorker.__init__
  STARTED   -- SpeechWorker.start() (called once, from SpeechManager.start())
  PROCESSING-- inside run()'s loop, once per dequeued utterance
  FINISHED  -- each utterance's engine.runAndWait() returning (loops back
               to waiting on the queue -- the OS thread itself keeps running)
  STOPPED   -- run() returns after dequeuing the sentinel from request_stop()
  DESTROYED -- only after SpeechManager.shutdown() confirms (via
               core.thread_safety.stop_and_release) that the thread has
               actually finished
"""

import logging
import queue

from PySide6.QtCore import QThread, Signal

from core.conversation_state import ConversationStateMachine
from core.thread_safety import log_thread_event, stop_and_release

logger = logging.getLogger("nova.threads")

_STOP = object()  # sentinel, distinguishable from any real string


class SpeechWorker(QThread):
    """One instance for the whole app lifetime. Do not create a second one
    -- SpeechManager owns the only instance and enforces that."""

    speaking_finished = Signal()

    def __init__(self, fsm: ConversationStateMachine | None):
        super().__init__()
        self._fsm = fsm
        self._queue: "queue.Queue[str | object]" = queue.Queue()

    def enqueue(self, text: str) -> None:
        self._queue.put(text)

    def request_stop(self) -> None:
        self._queue.put(_STOP)

    def run(self) -> None:
        log_thread_event("STARTED", self)

        # pyttsx3 on Windows drives SAPI5 through COM, and COM requires
        # each thread that touches it to initialize its own apartment
        # first. This is a separate, well-documented native crash source
        # from the QThread-lifetime issue -- distinct, but easy to mistake
        # for it, since it also only shows up on a background thread and
        # presents the same way (something gets spoken, then it dies).
        # pythoncom only exists on Windows (ships with pywin32); everywhere
        # else this is a no-op.
        com_initialized = False
        try:
            import pythoncom

            pythoncom.CoInitialize()
            com_initialized = True
        except ImportError:
            pass

        engine = None
        try:
            import pyttsx3

            engine = pyttsx3.init()
        except Exception:
            logger.exception("[THREAD] SpeechWorker failed to initialize pyttsx3 -- TTS disabled for this session")

        try:
            while True:
                item = self._queue.get()  # blocks -- this IS the thread's idle state, not busy-waiting
                if item is _STOP:
                    break

                logger.info("[THREAD] SpeechWorker PROCESSING: %r", item[:60])
                if self._fsm is not None:
                    self._fsm.on_speaking()
                try:
                    if engine is not None:
                        engine.say(item)
                        engine.runAndWait()
                except Exception:
                    logger.exception("[THREAD] SpeechWorker: engine.runAndWait() raised for %r", item[:60])
                finally:
                    if self._fsm is not None:
                        self._fsm.on_response_complete()
                    self.speaking_finished.emit()
        finally:
            if com_initialized:
                import pythoncom

                pythoncom.CoUninitialize()
            log_thread_event("STOPPED", self)


class SpeechManager:
    """
    Thin façade ChatPanel/reminder_alert talk to -- `speak(text)` just
    enqueues onto the one persistent SpeechWorker. No QThread is created
    or touched here at all; that's entirely SpeechWorker's job now.
    """

    def __init__(self, fsm: ConversationStateMachine):
        self._fsm = fsm
        self._worker = SpeechWorker(fsm)
        self._worker.start()

    def speak(self, text: str) -> None:
        if not text:
            return
        self._worker.enqueue(text)

    def shutdown(self, timeout_ms: int = 3000) -> None:
        """Called from app shutdown. Uses the shared safe-stop helper --
        never a bare wait()-then-proceed-anyway, which is the exact
        pattern that caused this bug the first three times."""
        stop_and_release(self._worker, self._worker.request_stop, timeout_ms, lambda: None)
