from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from core.api_client import NovaAPIClient
from core.speaker_verification import SpeakerVerifier

SAMPLE_COUNT = 5
SAMPLE_SECONDS = 3
SAMPLE_RATE = 16000


class RecordWorker(QThread):
    finished_ok = Signal(object)  # np.ndarray
    failed = Signal(str)

    def run(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd

            recording = sd.rec(SAMPLE_SECONDS * SAMPLE_RATE, samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocking=True)
            self.finished_ok.emit(np.asarray(recording).reshape(-1))
        except Exception as e:
            self.failed.emit(str(e))


class EnrollWorker(QThread):
    finished_ok = Signal(bool, str)

    def __init__(self, verifier: SpeakerVerifier, client: NovaAPIClient, recordings: list):
        super().__init__()
        self._verifier = verifier
        self._client = client
        self._recordings = recordings

    def run(self) -> None:
        import asyncio

        try:
            ok, message = asyncio.run(self._verifier.enroll(self._recordings, self._client))
            self.finished_ok.emit(ok, message)
        except Exception as e:
            self.finished_ok.emit(False, str(e))


class VoiceEnrollmentDialog(QDialog):
    """
    Spec section 9's "Voice" page, as much of it as makes sense inside the
    desktop agent's own window: record several natural samples (not one),
    show progress, allow retakes, then train. The recordings themselves
    are never sent anywhere -- SpeakerVerifier.enroll() computes an
    embedding from each one locally and only the embeddings leave this
    machine (see core/speaker_verification.py and the backend's
    /api/v1/speaker/enroll, which never receives audio).
    """

    def __init__(self, client: NovaAPIClient, verifier: SpeakerVerifier):
        super().__init__()
        self._client = client
        self._verifier = verifier
        self._recordings: list = []
        self._worker: QThread | None = None

        self.setWindowTitle("Set up voice verification")
        self.resize(360, 220)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Record a few samples of your own voice, speaking naturally "
            "(different sentences, normal volume). This lets Nova tell your "
            "voice apart from anyone else's before acting on a wake word."
        ))

        self.progress = QProgressBar()
        self.progress.setMaximum(SAMPLE_COUNT)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.status_label = QLabel(f"Sample 0/{SAMPLE_COUNT}")
        layout.addWidget(self.status_label)

        self.record_btn = QPushButton(f"Record sample ({SAMPLE_SECONDS}s)")
        self.record_btn.clicked.connect(self._record_next)
        layout.addWidget(self.record_btn)

        self.retake_btn = QPushButton("Retake last sample")
        self.retake_btn.clicked.connect(self._retake_last)
        self.retake_btn.setEnabled(False)
        layout.addWidget(self.retake_btn)

        self.train_btn = QPushButton("Train voice profile")
        self.train_btn.setEnabled(False)
        self.train_btn.clicked.connect(self._train)
        layout.addWidget(self.train_btn)

    def _record_next(self) -> None:
        self.record_btn.setEnabled(False)
        self.status_label.setText(f"Recording sample {len(self._recordings) + 1}/{SAMPLE_COUNT} — speak now…")

        self._worker = RecordWorker()
        self._worker.finished_ok.connect(self._on_sample_recorded)
        self._worker.failed.connect(self._on_record_failed)
        self._worker.start()

    def _on_sample_recorded(self, pcm) -> None:
        self._recordings.append(pcm)
        self.progress.setValue(len(self._recordings))
        self.status_label.setText(f"Sample {len(self._recordings)}/{SAMPLE_COUNT} captured.")
        self.retake_btn.setEnabled(True)

        if len(self._recordings) >= SAMPLE_COUNT:
            self.record_btn.setEnabled(False)
            self.train_btn.setEnabled(True)
            self.status_label.setText("All samples captured — ready to train.")
        else:
            self.record_btn.setEnabled(True)

    def _on_record_failed(self, error: str) -> None:
        self.record_btn.setEnabled(True)
        QMessageBox.warning(self, "Microphone error", error)

    def _retake_last(self) -> None:
        if self._recordings:
            self._recordings.pop()
            self.progress.setValue(len(self._recordings))
            self.status_label.setText(f"Sample {len(self._recordings)}/{SAMPLE_COUNT} — retake ready.")
            self.record_btn.setEnabled(True)
            self.train_btn.setEnabled(False)
        self.retake_btn.setEnabled(bool(self._recordings))

    def _train(self) -> None:
        self.train_btn.setEnabled(False)
        self.record_btn.setEnabled(False)
        self.retake_btn.setEnabled(False)
        self.status_label.setText("Training voice profile…")

        self._worker = EnrollWorker(self._verifier, self._client, list(self._recordings))
        self._worker.finished_ok.connect(self._on_trained)
        self._worker.start()

    def _on_trained(self, ok: bool, message: str) -> None:
        if ok:
            QMessageBox.information(self, "Voice verification ready", message)
            self.accept()
        else:
            QMessageBox.warning(self, "Training failed", message)
            self.train_btn.setEnabled(True)
            self.record_btn.setEnabled(True)
