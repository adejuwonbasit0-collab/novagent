from __future__ import annotations

from PySide6.QtCore import QThread, Signal
import time

from core.conversation_state import ConversationStateMachine
from core.speaker_verification import SpeakerVerifier


class VoiceListener(QThread):
    transcript = Signal(str)
    status = Signal(str)
    failed = Signal(str)

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
                    self._fsm.on_wake_detected()
                    self._fsm.on_verifying()
                    result = self._verifier.verify(pcm)

                    if not result.verified:
                        self.status.emit("Voice not recognized.")
                        self._fsm.on_rejected()
                        continue  # no session armed, no transcript emitted -- locked out

                    has_command = lowered != matched_prefix
                    self._fsm.on_verified(has_immediate_command=has_command)
                    if not has_command:
                        self.transcript.emit("")  # bare wake word -- chat panel replies "Yes, I'm listening"
                    else:
                        self.transcript.emit(words[len(matched_prefix) :].strip())

                elif self._fsm.is_active_conversation:
                    # Continuing an already-verified active conversation
                    # (spec section 6) -- no re-verification per sentence,
                    # only per wake event.
                    self._fsm.on_continuation()
                    self.transcript.emit(words)
        except Exception as exc:
            self._fsm.on_error()
            self.failed.emit(str(exc))


class SpeechSpeaker(QThread):
    finished_speaking = Signal()

    def __init__(self, text: str, fsm: ConversationStateMachine | None = None):
        super().__init__()
        self._text = text
        self._fsm = fsm

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
            if self._fsm is not None:
                self._fsm.on_speaking()
            import pyttsx3

            engine = pyttsx3.init()
            engine.say(self._text)
            engine.runAndWait()
        finally:
            if com_initialized:
                import pythoncom

                pythoncom.CoUninitialize()
            if self._fsm is not None:
                self._fsm.on_response_complete()
            self.finished_speaking.emit()
