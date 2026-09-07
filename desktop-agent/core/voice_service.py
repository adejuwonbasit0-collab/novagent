from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from core.api_client import NovaAPIClient
from core.conversation_state import ConversationStateMachine
from core.speaker_verification import SpeakerVerifier
from core.speech_manager import SpeechManager
from core.voice import VoiceListener
from config import settings


class StartupState(str, Enum):
    """Spec section 4's controlled startup sequence. AGENT_READY /
    WAIT_FOR_WAKE_WORD from the spec collapse into READY here -- once the
    listener thread has confirmed it's actually looping, "ready" and
    "waiting for the wake word" are the same observable state."""

    STARTING = "starting"
    INITIALIZING_SPEAKER_VERIFICATION = "initializing_speaker_verification"
    SYNCING_SPEAKER_PROFILE = "syncing_speaker_profile"
    INITIALIZING_MICROPHONE = "initializing_microphone"
    INITIALIZING_SPEECH_RECOGNITION = "initializing_speech_recognition"
    READY = "ready"
    FAILED = "failed"


class SpeakerSyncWorker(QThread):
    """Pulls the current speaker-verification template from the backend at
    startup so the gate reflects whatever was last enrolled/reset -- from
    this device or another one, or via the dashboard. Runs once per app
    launch; verify() itself never touches the network (see SpeakerVerifier).

    Moved here from ui/chat_panel.py: this is a core service concern, not
    a chat-window concern (spec section 9) -- it has to run and complete
    whether or not the user ever opens the chat panel."""

    finished_sync = Signal()

    def __init__(self, verifier: SpeakerVerifier, client: NovaAPIClient):
        super().__init__()
        self._verifier = verifier
        self._client = client

    def run(self) -> None:
        import asyncio

        try:
            asyncio.run(self._verifier.sync_from_backend(self._client))
        except Exception:
            pass  # offline at startup -- fall back to whatever's already cached locally
        finally:
            self.finished_sync.emit()


class VoiceService(QObject):
    """
    Owns everything that must keep running independent of whether the
    chat window exists (spec section 9): the conversation state machine,
    speaker verification, the wake-word/voice listener, and text-to-
    speech. ChatPanel (and anything else in ui/) observes and drives this
    service through its signals/methods; it never constructs or holds
    these objects itself, so closing/destroying the chat window can
    never touch -- let alone crash -- the actual listening pipeline.

    Also implements two fixes that don't fit naturally as a patch to the
    old ChatPanel-owned version:

    1. Controlled startup (spec section 4): the speaker-verification
       template is synced from the backend *before* the microphone/
       wake-word pipeline is armed, instead of both racing to start at
       once.

    2. Don't speak before the audio system is ready (spec section 5):
       previously, `start_listening()` said "I'm listening for Nova"
       unconditionally, synchronously, the instant the Start-listening
       toggle flipped on -- before VoiceListener's thread had done
       anything at all, let alone confirmed the mic/recognizer imports
       and setup actually succeeded. Now the greeting is deferred until
       VoiceListener's *first* `status` emission, which only happens
       after it's past its imports and mic setup and has actually
       entered its listen loop -- the earliest point at which "ready" is
       true rather than merely attempted.
    """

    startup_state_changed = Signal(object)  # StartupState
    transcript = Signal(str)
    status = Signal(str)
    error = Signal(str)
    listening_changed = Signal(bool)

    def __init__(self, client: NovaAPIClient):
        super().__init__()
        self._client = client
        self.fsm = ConversationStateMachine()
        self.verifier = SpeakerVerifier()
        self._speech = SpeechManager(self.fsm)
        self._voice_listener: VoiceListener | None = None
        self._sync_worker: SpeakerSyncWorker | None = None
        self._speak_when_ready = False
        self._first_status_seen = False
        self._startup_state = StartupState.STARTING
        self._auto_retry_count = 0
        self._auto_retry_cap = 5  # after this many consecutive failures, stop retrying and wait for a manual Resume

    @property
    def is_listening(self) -> bool:
        return self._voice_listener is not None

    def speak(self, text: str) -> None:
        self._speech.speak(text)

    def _set_startup_state(self, state: StartupState) -> None:
        self._startup_state = state
        self.startup_state_changed.emit(state)

    # ---- controlled startup (spec section 4) ----

    def start(self) -> None:
        """Kicks off the one-time controlled startup sequence: sync the
        speaker profile, THEN arm the microphone/wake-word pipeline, THEN
        (once VoiceListener confirms it's actually listening) speak the
        greeting. Safe to call once; a second call is a no-op."""
        if self._sync_worker is not None:
            return
        self._set_startup_state(StartupState.INITIALIZING_SPEAKER_VERIFICATION)
        self._sync_worker = SpeakerSyncWorker(self.verifier, self._client)
        self._sync_worker.finished_sync.connect(self._on_speaker_sync_done)
        self._set_startup_state(StartupState.SYNCING_SPEAKER_PROFILE)
        self._sync_worker.start()

    def _on_speaker_sync_done(self) -> None:
        self._start_listening_internal(speak_when_ready=True)

    # ---- explicit (re)start, e.g. from the chat panel's toggle or the
    # bubble's Resume control -- not the first-run sequence, so no
    # greeting delay is needed: the pipeline already proved itself once
    # this session. ----

    def start_listening(self) -> None:
        self._start_listening_internal(speak_when_ready=False)

    def _start_listening_internal(self, speak_when_ready: bool) -> None:
        if self._voice_listener is not None:
            return
        self._speak_when_ready = speak_when_ready
        self._first_status_seen = False
        self._set_startup_state(StartupState.INITIALIZING_MICROPHONE)

        listener = VoiceListener(settings.ASSISTANT_NAME, self.verifier, self.fsm, settings.VOICE_LANGUAGE)
        listener.transcript.connect(self.transcript)
        listener.status.connect(self._on_status)
        listener.failed.connect(self._on_failed)
        # See core/voice.py's class-level comment: these run on the fsm's
        # own (main) thread via Qt's automatic cross-thread queuing,
        # never called directly from the worker thread.
        listener.wake_detected.connect(self.fsm.on_wake_detected)
        listener.verifying.connect(self.fsm.on_verifying)
        listener.verified.connect(self.fsm.on_verified)
        listener.rejected.connect(self.fsm.on_rejected)
        listener.continuation.connect(self.fsm.on_continuation)
        listener.finished.connect(lambda: self.listening_changed.emit(False))

        self._voice_listener = listener
        self._set_startup_state(StartupState.INITIALIZING_SPEECH_RECOGNITION)
        listener.start()
        self.fsm.start()
        self.listening_changed.emit(True)

    def _on_status(self, text: str) -> None:
        if not self._first_status_seen:
            self._first_status_seen = True
            self._set_startup_state(StartupState.READY)
            if self._speak_when_ready:
                self.speak(f"I'm listening for {settings.ASSISTANT_NAME}.")
        # A real status emission proves the listener is actively cycling,
        # not just that it started -- this is what "recovered" means, so
        # this is where the auto-retry counter resets. Without a reset,
        # one rough patch early on (a couple of dropped wifi packets, say)
        # would permanently use up retries that should have been reserved
        # for a later, unrelated failure.
        self._auto_retry_count = 0
        self.status.emit(text)

    def _on_failed(self, error: str) -> None:
        # Root cause of "sometimes it just stops and doesn't reply": most
        # failures here used to be permanent -- VoiceListener.run() ending
        # (see core/voice.py's per-iteration exception handling fix) meant
        # no more recording cycles, ever, until something noticed and
        # manually restarted listening. A single bad network response
        # from the speech API, or one bad audio buffer, should not require
        # a restart. This retries automatically, with a short backoff and
        # a cap so a persistent problem (no mic present at all, etc.)
        # still surfaces as FAILED instead of retrying forever.
        self._set_startup_state(StartupState.FAILED)
        self.fsm.on_error()
        self.error.emit(error)

        listener = self._voice_listener
        if listener is not None:
            listener.wait(6000)  # run() already returned by the time `failed` fired -- confirms it, doesn't guess
            if self._voice_listener is listener:
                self._voice_listener = None

        self._auto_retry_count += 1
        if self._auto_retry_count <= self._auto_retry_cap:
            QTimer.singleShot(3000, self._retry_after_failure)
        # else: give up automatically retrying -- stays in FAILED/OFFLINE-
        # looking state until the user hits Resume from the bubble, which
        # calls start_listening() (and that resets the counter via the
        # next successful _on_status, same as any other recovery).

    def _retry_after_failure(self) -> None:
        # The user may have explicitly stopped/paused in the 3s window
        # between the failure and this firing -- an auto-retry must never
        # override that and start listening again against their wishes.
        if self.fsm.is_stopped or self.fsm.is_paused:
            return
        self._start_listening_internal(speak_when_ready=False)

    # ---- stop / shutdown -- see ui/chat_panel.py's _toggle_voice (this
    # mirrors that logic exactly; kept in one place now instead of two) ----

    def stop_listening(self) -> None:
        if self._voice_listener is None:
            return
        listener = self._voice_listener
        listener.stop()
        if listener.wait(6000):
            self._voice_listener = None
        else:
            listener.finished.connect(
                lambda l=listener: setattr(self, "_voice_listener", None) if self._voice_listener is l else None
            )
        self.fsm.stop()
        self.listening_changed.emit(False)

    def shutdown(self) -> None:
        """Full teardown for app exit (spec section 18's shutdown
        order): stop the listener first (releases the mic), then wait
        for the sync worker if it's somehow still going, then let
        SpeechManager drain/wait for anything mid-utterance. Every wait()
        here has a real timeout and nothing nulls a reference without
        one succeeding -- see SpeechManager and VoiceListener's own
        docstrings for why that matters."""
        self.stop_listening()
        if self._voice_listener is not None:
            self._voice_listener.wait(6000)
        if self._sync_worker is not None and self._sync_worker.isRunning():
            self._sync_worker.wait(3000)
        self._speech.shutdown()
