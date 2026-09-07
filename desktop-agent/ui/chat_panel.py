from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.api_client import ChatReply, NovaAPIClient, ToolCallResult
from core.conversation_state import ConversationState, ConversationStateMachine
from core.voice import VoiceListener
from core.speaker_verification import SpeakerVerifier
from core.speech_manager import SpeechManager
from core.local_router import route_locally
from core.thread_safety import log_thread_event, stop_and_release
from ui.voice_enrollment import VoiceEnrollmentDialog
from config import settings

logger = logging.getLogger("nova.threads")


class SpeakerSyncWorker(QThread):
    """Pulls the current speaker-verification template from the backend at
    startup so the gate reflects whatever was last enrolled/reset -- from
    this device or another one, or via the dashboard. Runs once per app
    launch; verify() itself never touches the network (see SpeakerVerifier)."""

    finished_sync = Signal()

    def __init__(self, verifier: SpeakerVerifier, client: NovaAPIClient):
        super().__init__()
        self._verifier = verifier
        self._client = client

    def run(self) -> None:
        log_thread_event("STARTED", self)
        import asyncio

        try:
            asyncio.run(self._verifier.sync_from_backend(self._client))
        except Exception:
            pass  # offline at startup -- fall back to whatever's already cached locally
        finally:
            log_thread_event("STOPPED", self)
            self.finished_sync.emit()


class ChatWorker(QThread):
    """Runs the async API call off the UI thread — PySide6 doesn't mix with
    asyncio directly, so each request gets its own event loop in a worker
    thread rather than blocking the GUI."""

    finished_ok = Signal(object)  # ChatReply
    failed = Signal(str)

    def __init__(self, client: NovaAPIClient, message: str):
        super().__init__()
        self._client = client
        self._message = message

    def run(self) -> None:
        log_thread_event("STARTED", self)
        import asyncio

        try:
            reply = asyncio.run(self._client.chat(self._message))
            self.finished_ok.emit(reply)
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            log_thread_event("STOPPED", self)


class ConfirmWorker(QThread):
    finished_ok = Signal(object)  # ToolCallResult
    failed = Signal(str)

    def __init__(self, client: NovaAPIClient, pending_id: str):
        super().__init__()
        self._client = client
        self._pending_id = pending_id

    def run(self) -> None:
        log_thread_event("STARTED", self)
        import asyncio

        try:
            result = asyncio.run(self._client.confirm_pending(self._pending_id))
            self.finished_ok.emit(result)
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            log_thread_event("STOPPED", self)


class DirectToolWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, client: NovaAPIClient, tool_name: str, params: dict):
        super().__init__()
        self._client = client
        self._tool_name = tool_name
        self._params = params

    def run(self) -> None:
        log_thread_event("STARTED", self)
        import asyncio

        try:
            result = asyncio.run(self._client.execute_tool(self._tool_name, self._params))
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            log_thread_event("STOPPED", self)


class ChatPanel(QWidget):
    def __init__(self, client: NovaAPIClient):
        super().__init__()
        self._client = client
        self._worker: QThread | None = None
        self._voice_listener: VoiceListener | None = None

        # Single source of truth for "what is Nova doing right now" (spec
        # section 36) -- the bubble, this panel, and VoiceListener all
        # react to or drive the same instance rather than each tracking
        # their own notion of state. Public so main.py can wire it
        # straight to the bubble and to the bubble's Pause/Resume/Stop
        # controls (spec section 37).
        self.fsm = ConversationStateMachine()
        self.fsm.state_changed.connect(self._on_fsm_state_changed)
        self._speech = SpeechManager(self.fsm)

        self._verifier = SpeakerVerifier()
        self._sync_worker = SpeakerSyncWorker(self._verifier, client)
        self._sync_worker.start()

        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Nova")
        self.resize(380, 480)

        layout = QVBoxLayout(self)

        self.history = QTextEdit()
        self.history.setReadOnly(True)
        layout.addWidget(self.history)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask Nova anything…")
        self.input.returnPressed.connect(self._on_submit)
        layout.addWidget(self.input)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self._on_submit)
        layout.addWidget(self.send_btn)

        self.listen_btn = QPushButton(f"Start listening for {settings.ASSISTANT_NAME}")
        self.listen_btn.setCheckable(True)
        self.listen_btn.toggled.connect(self._toggle_voice)
        layout.addWidget(self.listen_btn)

        self.voice_setup_btn = QPushButton("Set up voice verification")
        self.voice_setup_btn.clicked.connect(self._open_voice_enrollment)
        layout.addWidget(self.voice_setup_btn)

    def start_listening(self) -> None:
        if not self.listen_btn.isChecked():
            self.listen_btn.setChecked(True)
            # Do NOT speak here. Previously this spoke "I'm listening for
            # Nova" immediately, before the microphone/speech-recognition
            # stack in VoiceListener had actually finished initializing --
            # if anything in that init failed or was still mid-import when
            # a second _speak() or an error path fired moments later, that
            # was the exact race that produced overlapping/mismanaged
            # speech threads. Now the greeting is deferred to
            # _on_voice_ready, which only fires once VoiceListener's own
            # run() has successfully imported everything and constructed
            # its recognizer -- confirmed ready, not just "started."

    def stop_listening(self) -> None:
        if self.listen_btn.isChecked():
            self.listen_btn.setChecked(False)

    def _append(self, who: str, text: str) -> None:
        self.history.append(f"<b>{who}:</b> {text}")

    def _on_fsm_state_changed(self, state: ConversationState) -> None:
        """Keeps the listen button's label/checked state honest even when
        the transition originated from the bubble's context menu rather
        than this button -- e.g. Stop from the bubble shouldn't leave the
        button showing 'Start listening' as still checked."""
        if state == ConversationState.STOPPED:
            self.listen_btn.blockSignals(True)
            self.listen_btn.setChecked(False)
            self.listen_btn.blockSignals(False)
            self.listen_btn.setText(f"Start listening for {settings.ASSISTANT_NAME}")
        elif state == ConversationState.PAUSED:
            self.listen_btn.setText("Paused — right-click the bubble to resume")
        elif state in (ConversationState.LISTENING, ConversationState.ACTIVE_CONVERSATION) and not self.listen_btn.isChecked():
            self.listen_btn.blockSignals(True)
            self.listen_btn.setChecked(True)
            self.listen_btn.blockSignals(False)
            self.listen_btn.setText(f"Listening for {settings.ASSISTANT_NAME}")

    def _open_voice_enrollment(self) -> None:
        was_listening = self.listen_btn.isChecked()
        if was_listening:
            self.listen_btn.setChecked(False)  # pause wake-word listening while the mic is used for enrollment

        dialog = VoiceEnrollmentDialog(self._client, self._verifier)
        dialog.exec()

        if was_listening:
            self.listen_btn.setChecked(True)

    def _toggle_voice(self, enabled: bool) -> None:
        if enabled:
            self._voice_listener = VoiceListener(settings.ASSISTANT_NAME, self._verifier, self.fsm, settings.VOICE_LANGUAGE)
            self._voice_listener.transcript.connect(self._on_voice_transcript)
            self._voice_listener.status.connect(self._on_voice_status)
            self._voice_listener.failed.connect(self._on_voice_error)
            self._voice_listener.ready.connect(self._on_voice_ready)
            self._voice_listener.finished.connect(lambda: self.listen_btn.setChecked(False))
            self._voice_listener.start()
            self.fsm.start()
        elif self._voice_listener:
            # `sd.rec()` inside VoiceListener.run() blocks for up to 5
            # seconds per cycle; stop() calls sd.stop() to abort that
            # blocking call from here, but that's not instantaneous.
            # stop_and_release (core/thread_safety.py) is the one place
            # this "wait, then only release if actually finished" logic
            # lives now -- see that module's docstring for why this used
            # to be reimplemented ad hoc in three different places, and
            # why one of those three (closeEvent) still had the broken
            # version until this change.
            listener = self._voice_listener
            stop_and_release(listener, listener.stop, 6000, lambda: setattr(self, "_voice_listener", None))
            self.fsm.stop()

    def _on_voice_ready(self) -> None:
        # Fires once per VoiceListener, right before it enters its listen
        # loop -- this is the actual "audio system confirmed ready"
        # moment, not just "the thread object was started."
        self._speak(f"I'm listening for {settings.ASSISTANT_NAME}.")

    def _on_voice_transcript(self, message: str) -> None:
        # WAKE_DETECTED/VERIFYING/rejection are handled inside VoiceListener
        # via direct fsm calls (core/voice.py) -- by the time a transcript
        # reaches here, verification already passed.
        if not message:
            self._speak(f"Yes, I'm listening.")
            return
        self._submit_message(message)

    def _on_voice_error(self, error: str) -> None:
        self.listen_btn.setChecked(False)
        self._append("Nova", f"Microphone error: {error}")
        self._speak(f"I cannot use the microphone. {error}")

    def _on_voice_status(self, text: str) -> None:
        if not self.listen_btn.isChecked():
            return
        if text.startswith("Speech service unavailable") or text.startswith("Microphone"):
            self._append("Nova", text)
            self._speak(text)

    def _speak(self, text: str) -> None:
        self._speech.speak(text)

    def _on_submit(self) -> None:
        message = self.input.text().strip()
        if not message:
            return
        self._submit_message(message)

    def _submit_message(self, message: str) -> None:
        # Same crash class as the SpeechManager fix above, different
        # attribute: self._worker gets reassigned on every call, and a
        # second voice-triggered command arriving while the first is
        # still in flight (e.g. two quick follow-ups in one active-
        # conversation session, backend still answering the first) would
        # silently drop the reference to a still-running QThread and
        # crash the same way. The Send button being disabled only stops
        # a second *manual* click -- it doesn't stop a second transcript
        # arriving from VoiceListener, so that path needs its own guard.
        if self._worker is not None and self._worker.isRunning():
            self._append("Nova", "Still working on the last request — one moment.")
            return

        self._append("You", message)
        self.input.clear()
        self.input.setEnabled(False)
        self.send_btn.setEnabled(False)

        routed = route_locally(message)
        if isinstance(routed, dict) and "unsupported" in routed:
            # Recognized as a local-sounding request for a capability that
            # doesn't exist end-to-end yet (spec section 47: never let a
            # command pretend to work). Answered directly, zero network
            # calls, instead of falling through to the cloud LLM, which
            # has no tool for this either and might otherwise imply it
            # happened.
            self._append("Nova", routed["unsupported"])
            self._speak(routed["unsupported"])
            self.input.setEnabled(True)
            self.send_btn.setEnabled(True)
            return

        if routed is not None:
            self.fsm.on_executing()
            self._worker = DirectToolWorker(self._client, routed.tool_name, routed.params)
            self._worker.finished_ok.connect(self._on_direct_reply)
            self._worker.failed.connect(self._on_error)
            self._worker.start()
            return

        self.fsm.on_thinking()
        self._worker = ChatWorker(self._client, message)
        self._worker.finished_ok.connect(self._on_reply)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _on_reply(self, reply: ChatReply) -> None:
        self._append("Nova", reply.reply)
        self._speak(reply.reply)  # SpeechSpeaker drives fsm -> SPEAKING -> on_response_complete

        for call in reply.tool_calls:
            if call.result == "REQUIRES_CONFIRMATION":
                self._handle_confirmation_needed(call)
            elif call.result == "DENIED":
                self._append("Nova", f"⚠️ I don't have permission to do that ({call.tool_name}).")
            elif call.result == "FAILURE":
                self._append("Nova", f"⚠️ {call.tool_name} failed: {call.error}")
            # SUCCESS: reply.reply from the model already describes it; the
            # raw call.data is available here for a richer UI card later.

        self.input.setEnabled(True)
        self.send_btn.setEnabled(True)

    def _on_direct_reply(self, result: ToolCallResult) -> None:
        # Previously had no REQUIRES_CONFIRMATION case, so a locally
        # fast-pathed high-risk tool (e.g. "shut down my computer") fell
        # into the generic failure branch and told the user Nova "could
        # not complete" the request -- even though the server correctly
        # withheld the action pending confirmation. Route it through the
        # same dialog the cloud/LLM path already uses.
        if result.result == "REQUIRES_CONFIRMATION":
            self._handle_confirmation_needed(result)
            self.input.setEnabled(True)
            self.send_btn.setEnabled(True)
            return

        if result.result == "SUCCESS":
            message = result.message or f"Done: {result.tool_name}"
        elif result.result == "DENIED":
            message = f"I need the {result.error or 'required'} permission before I can do that."
        else:
            message = result.error or f"I could not complete {result.tool_name}."
        self._append("Nova", message)
        self._speak(message)
        self.input.setEnabled(True)
        self.send_btn.setEnabled(True)

    def _on_error(self, error: str) -> None:
        self._append("Nova", f"⚠️ Something went wrong: {error}")
        self.fsm.on_error()
        self._speak("I couldn't complete that request.")
        self.input.setEnabled(True)
        self.send_btn.setEnabled(True)

    def _handle_confirmation_needed(self, call: ToolCallResult) -> None:
        """
        Mirrors spec section 5's exact example: high-risk actions get a
        real modal confirmation, never a silent auto-run — this is the UI
        half of the backend's PendingToolCall gate.
        """
        box = QMessageBox(self)
        box.setWindowTitle("Confirm action")
        box.setText(call.message or f"Nova wants to run '{call.tool_name}'. Continue?")
        box.setStandardButtons(QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)

        if box.exec() == QMessageBox.StandardButton.Yes and call.pending_id:
            self.fsm.on_executing()
            confirm_worker = ConfirmWorker(self._client, call.pending_id)
            confirm_worker.finished_ok.connect(
                lambda result: self._append("Nova", result.message or f"{result.tool_name}: {result.result}")
            )
            confirm_worker.failed.connect(lambda err: self._append("Nova", f"⚠️ Confirmation failed: {err}"))
            confirm_worker.finished.connect(self.fsm.on_response_complete)
            confirm_worker.start()
            self._confirm_worker = confirm_worker  # keep a reference so it isn't garbage-collected mid-run
        else:
            self._append("Nova", "Okay, I won't do that.")

    def closeEvent(self, event) -> None:  # noqa: N802
        # Previously: `self._voice_listener.wait(2000)` followed by an
        # UNCONDITIONAL `self._voice_listener = None` regardless of
        # whether wait() actually succeeded. sd.rec() can block up to 5s,
        # so a 2s wait routinely timed out, and this then dropped the
        # reference to a QThread that was, provably, still running --
        # exactly the bug this whole file has been fixed for twice
        # already in other methods (_toggle_voice's off-branch,
        # main.py's _shutdown_threads), just missed here. Routed through
        # the same shared helper now so this can't happen a third time.
        self.stop_listening()
        listener = self._voice_listener
        stop_and_release(listener, (listener.stop if listener else lambda: None), 6000, lambda: setattr(self, "_voice_listener", None))
        self._speech.shutdown()
        event.accept()
