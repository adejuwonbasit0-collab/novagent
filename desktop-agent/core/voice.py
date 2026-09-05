from __future__ import annotations

from PySide6.QtCore import QThread, Signal
import time


class VoiceListener(QThread):
    transcript = Signal(str)
    status = Signal(str)
    failed = Signal(str)

    def __init__(self, wake_name: str, language: str = "en-US"):
        super().__init__()
        self._wake_name = wake_name.lower().strip()
        self._language = language
        self._running = True
        self._armed_until = 0.0

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
                recording = sd.rec(5 * 16000, samplerate=16000, channels=1, dtype="int16", blocking=True)
                audio = sr.AudioData(np.asarray(recording).tobytes(), 16000, 2)
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
                if matched_prefix == self._wake_name and lowered == self._wake_name:
                    self._armed_until = time.monotonic() + 12
                    self.transcript.emit("")
                elif matched_prefix:
                    self._armed_until = time.monotonic() + 12
                    self.transcript.emit(words[len(matched_prefix) :].strip())
                elif time.monotonic() < self._armed_until:
                    self._armed_until = 0.0
                    self.transcript.emit(words)
        except Exception as exc:
            self.failed.emit(str(exc))


class SpeechSpeaker(QThread):
    finished_speaking = Signal()

    def __init__(self, text: str):
        super().__init__()
        self._text = text

    def run(self) -> None:
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.say(self._text)
            engine.runAndWait()
        finally:
            self.finished_speaking.emit()