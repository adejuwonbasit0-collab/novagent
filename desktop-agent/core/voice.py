from __future__ import annotations

from PySide6.QtCore import QThread, Signal
import time

from core.conversation_state import ConversationStateMachine
from core.speaker_verification import SpeakerVerifier


class VoiceListener(QThread):
    transcript = Signal(str)
    status = Signal(str)
    failed = Signal(str)

    # Previously this thread called self._fsm.on_wake_detected() /
    # on_verifying() / on_verified() / on_rejected() / on_error() directly
    # from run() -- i.e. from the worker OS thread. ConversationStateMachine
    # lives on the main thread and those methods touch a QTimer
    # (_arm_timeout/_check_timeout) and, in on_rejected(), call
    # QTimer.singleShot(...) -- both of which are only well-defined when
    # done on the object's own thread. QTimer.singleShot in particular is
    # documented as running in the calling thread; called from a QThread
    # that never runs its own event loop (this one doesn't -- run() is
    # overridden, exec() is never called), the timer it creates has
    # nothing to pump it and its callback never fires. Concretely: a
    # rejected voice would transition to LOCKED and then never
    # auto-recover back to LISTENING, since the 1200ms singleShot inside
    # on_rejected() silently never elapses.
    #
    # Fixed by emitting signals instead and letting whoever owns both this
    # listener and the fsm connect them -- cross-thread connections are
    # queued automatically, so the fsm's own methods (and any QTimer they
    # touch) only ever run on the thread that actually owns them.
    wake_detected = Signal()
    verifying = Signal()
    verified = Signal(bool)  # has_immediate_command
    rejected = Signal()
    continuation = Signal()

    def __init__(
        self,
        wake_name: str,
        verifier: SpeakerVerifier,
        fsm: ConversationStateMachine,
        language: str = "en-US",
    ):
        super().__init__()
        self._wake_name = wake_name.lower().strip()
        self._verifier = verifier
        self._fsm = fsm
        self._language = language
        self._running = True

    def stop(self) -> None:
        self._running = False
        try:
            import sounddevice as sd

            sd.stop()
        except Exception:
            pass

    def run(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd
            import speech_recognition as sr

            recognizer = sr.Recognizer()
            recognizer.pause_threshold = 0.8
            recognizer.non_speaking_duration = 0.3
            self.status.emit(f"Listening for {self._wake_name.title()}")
            while self._running:
                # Paused/stopped (spec section 37, controlled from the
                # bubble): release the mic rather than recording into a
                # buffer nothing will act on -- this is what makes Pause
                # actually pause, not just repaint the bubble.
                if self._fsm.is_paused or self._fsm.is_stopped:
                    time.sleep(0.3)
                    continue

                recording = sd.rec(5 * 16000, samplerate=16000, channels=1, dtype="int16", blocking=True)

                # A pause/stop request that arrived mid-recording -- drop
                # this buffer rather than processing audio captured after
                # the user asked Nova to stop listening.
                if self._fsm.is_paused or self._fsm.is_stopped:
                    continue

                pcm = np.asarray(recording).reshape(-1)
                audio = sr.AudioData(pcm.tobytes(), 16000, 2)
                try:
                    words = recognizer.recognize_google(audio, language=self._language).strip()
                except sr.UnknownValueError:
                    self.status.emit(f"I did not understand that. Say Hey {self._wake_name.title()}.")
                    continue
                except sr.RequestError as exc:
                    self.status.emit(f"Speech service unavailable: {exc}")
                    continue
                except Exception as exc:
                    # THE likely cause of "sometimes it just stops and
                    # doesn't reply": recognize_google talks to Google's
                    # free web speech endpoint over plain urllib, and in
                    # practice raises more than just sr.RequestError on a
                    # flaky connection -- raw URLError/socket timeouts/
                    # connection resets are common and are NOT sr.RequestError
                    # in every version of this library. Before this fix,
                    # anything other than those two specific exception types
                    # propagated out of this per-iteration try/except,
                    # through the while loop, into the outer except at the
                    # bottom of run() -- which ends run() entirely. One
                    # transient network hiccup during a single 5-second
                    # recording cycle would permanently kill the whole
                    # wake-word loop: no crash, no visible error the user
                    # would necessarily see (especially voice-only, chat
                    # panel never opened), just silence forever until the
                    # app is restarted. A single bad recognition attempt
                    # should never end the ability to try again.
                    self.status.emit(f"Speech recognition error: {exc}")
                    continue

                lowered = words.lower()
                wake_prefixes = (self._wake_name, f"hey {self._wake_name}")
                matched_prefix = next(
                    (prefix for prefix in wake_prefixes if lowered == prefix or lowered.startswith(prefix + " ")),
                    None,
                )

                if matched_prefix is not None:
                    # A wake phrase was heard -- this is the moment the
                    # bubble should visibly "wake" (soundwave). Verification
                    # runs on this exact buffer, no extra recording, so
                    # there's no added delay before transcript/unrecognized
                    # follows.
                    self.wake_detected.emit()
                    self.verifying.emit()
                    try:
                        result = self._verifier.verify(pcm)
                    except Exception as exc:
                        # Same reasoning as the recognize_google catch above:
                        # this used to be able to propagate out of the loop
                        # entirely and end run() on a single bad buffer. Fail
                        # CLOSED (treat as rejected, not as "skip and keep
                        # whatever state we had") -- an error computing
                        # whether the voice matches is not evidence that it
                        # does, and the security gate (spec section 8) must
                        # not have a silent bypass.
                        self.status.emit(f"Speaker verification error: {exc}")
                        self.rejected.emit()
                        continue

                    if not result.verified:
                        self.status.emit("Voice not recognized.")
                        self.rejected.emit()
                        continue  # no session armed, no transcript emitted -- locked out

                    has_command = lowered != matched_prefix
                    self.verified.emit(has_command)
                    if not has_command:
                        self.transcript.emit("")  # bare wake word -- chat panel replies "Yes, I'm listening"
                    else:
                        self.transcript.emit(words[len(matched_prefix) :].strip())

                elif self._fsm.is_active_conversation:
                    # Continuing an already-verified active conversation
                    # (spec section 6) -- no re-verification per sentence,
                    # only per wake event.
                    self.continuation.emit()
                    self.transcript.emit(words)
        except Exception as exc:
            # fsm.on_error() is intentionally NOT called here -- it would be
            # a cross-thread call into a QObject that lives on the main
            # thread (see the class-level comment). `failed` is already
            # connected by whoever owns this listener; on_error() belongs
            # in that (main-thread) handler instead.
            self.failed.emit(str(exc))


class SpeechSpeaker(QThread):
    finished_speaking = Signal()
    # BUG FIX: this class used to take `fsm` directly and call
    # self._fsm.on_speaking() / self._fsm.on_response_complete() from
    # inside run() -- i.e. from this QThread's own worker thread, not the
    # main thread ConversationStateMachine (and its QTimer) actually
    # lives on. That's the identical bug VoiceListener had (see the long
    # comment at the top of this file) and was fixed there by emitting
    # signals instead of touching the fsm directly -- but the same fix
    # was never applied here. This is exactly what produced
    # "QObject::startTimer: Timers cannot be started from another
    # thread" / "QObject::killTimer: ..." in practice: on_response_complete()
    # (called on every single spoken reply) arms conversation_state.py's
    # inactivity QTimer, from the wrong thread, every time Nova finishes
    # talking. Fixed the same way: emit signals, let SpeechManager (which
    # owns the fsm and lives on the main thread) connect them.
    speaking = Signal()

    def __init__(self, text: str):
        super().__init__()
        self._text = text

    def run(self) -> None:
        # pyttsx3 on Windows drives SAPI5 through COM, and COM requires
        # each thread that touches it to initialize its own apartment
        # first. pyttsx3.init() from a QThread with no CoInitialize() call
        # is a separate, well-documented native crash source on Windows —
        # distinct from (but easy to mistake for) the QThread-lifetime bug
        # SpeechManager fixes, since it also only shows up when TTS runs
        # on a background thread and can present the same way (something
        # gets spoken, then the process dies). pythoncom only exists on
        # Windows (it ships with pywin32); everywhere else this is a no-op.
        com_initialized = False
        try:
            import pythoncom

            pythoncom.CoInitialize()
            com_initialized = True
        except ImportError:
            pass  # not on Windows, or pywin32 isn't installed — nothing to do

        try:
            self.speaking.emit()
            import pyttsx3

            engine = pyttsx3.init()
            engine.say(self._text)
            engine.runAndWait()
        finally:
            if com_initialized:
                import pythoncom

                pythoncom.CoUninitialize()
            self.finished_speaking.emit()
