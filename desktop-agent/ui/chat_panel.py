from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.api_client import ChatReply, NovaAPIClient, ToolCallResult
from ui.bubble import AgentState
from core.voice import SpeechSpeaker, VoiceListener
from config import settings
import re
from pathlib import Path


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
        import asyncio

        try:
            reply = asyncio.run(self._client.chat(self._message))
            self.finished_ok.emit(reply)
        except Exception as e:
            self.failed.emit(str(e))


class ConfirmWorker(QThread):
    finished_ok = Signal(object)  # ToolCallResult
    failed = Signal(str)

    def __init__(self, client: NovaAPIClient, pending_id: str):
        super().__init__()
        self._client = client
        self._pending_id = pending_id

    def run(self) -> None:
        import asyncio

        try:
            result = asyncio.run(self._client.confirm_pending(self._pending_id))
            self.finished_ok.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


class DirectToolWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, client: NovaAPIClient, tool_name: str, params: dict):
        super().__init__()
        self._client = client
        self._tool_name = tool_name
        self._params = params

    def run(self) -> None:
        import asyncio

        try:
            result = asyncio.run(self._client.execute_tool(self._tool_name, self._params))
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


def _local_command(message: str) -> tuple[str, dict] | None:
    """Recognize deterministic computer actions without asking an LLM."""
    text = message.strip()
    lowered = text.lower()
    if re.search(r"\b(open|launch|start)\b.*\b(chrome|google chrome)\b", lowered):
        return "open_application", {"app_name": "chrome"}
    if re.search(r"\b(open|launch)\b.*\b(notepad)\b", lowered):
        return "open_application", {"app_name": "notepad.exe"}
    if lowered in {"open settings", "go to settings"}:
        return "open_application", {"app_name": "ms-settings:"}
    if lowered in {"open control panel", "go to control panel"}:
        return "open_application", {"app_name": "control.exe"}
    code_match = re.search(r"(?:open|launch) (.+?) in (?:visual studio code|vs code|vscode)$", text, re.I)
    if code_match:
        return "open_folder_in_application", {"path": code_match.group(1).strip().strip('"'), "app_name": "Visual Studio Code"}
    folder_match = re.search(r"(?:create|make) (?:a )?folder(?: named| called)?\s+(.+)$", text, re.I)
    if folder_match:
        name = folder_match.group(1).strip().strip('"')
        return "create_folder", {"path": str(Path.home() / "Desktop" / name)}
    return None


class ChatPanel(QWidget):
    state_changed = Signal(AgentState)

    def __init__(self, client: NovaAPIClient):
        super().__init__()
        self._client = client
        self._worker: QThread | None = None
        self._voice_listener: VoiceListener | None = None
        self._speaker: SpeechSpeaker | None = None

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

    def start_listening(self) -> None:
        if not self.listen_btn.isChecked():
            self.listen_btn.setChecked(True)
            self._speak(f"I'm listening for {settings.ASSISTANT_NAME}.")

    def stop_listening(self) -> None:
        if self.listen_btn.isChecked():
            self.listen_btn.setChecked(False)

    def _append(self, who: str, text: str) -> None:
        self.history.append(f"<b>{who}:</b> {text}")

    def _toggle_voice(self, enabled: bool) -> None:
        if enabled:
            self._voice_listener = VoiceListener(settings.ASSISTANT_NAME, settings.VOICE_LANGUAGE)
            self._voice_listener.transcript.connect(self._on_voice_transcript)
            self._voice_listener.status.connect(self._on_voice_status)
            self._voice_listener.failed.connect(self._on_voice_error)
            self._voice_listener.finished.connect(lambda: self.listen_btn.setChecked(False))
            self._voice_listener.start()
            self.state_changed.emit(AgentState.LISTENING)
        elif self._voice_listener:
            listener = self._voice_listener
            listener.stop()
            listener.wait(2000)
            self._voice_listener = None
            self.listen_btn.setText(f"Start listening for {settings.ASSISTANT_NAME}")
            self.state_changed.emit(AgentState.IDLE)

    def _on_voice_transcript(self, message: str) -> None:
        if not message:
            self._speak(f"Yes, I'm listening.")
            return
        self._submit_message(message)

    def _on_voice_error(self, error: str) -> None:
        self.listen_btn.setChecked(False)
        self._append("Nova", f"Microphone error: {error}")
        self._speak(f"I cannot use the microphone. {error}")
        self.state_changed.emit(AgentState.IDLE)

    def _on_voice_status(self, text: str) -> None:
        self.listen_btn.setText(text)
        if text.startswith("Speech service unavailable") or text.startswith("Microphone"):
            self._append("Nova", text)
            self._speak(text)

    def _speak(self, text: str) -> None:
        if not text:
            return
        self._speaker = SpeechSpeaker(text)
        self._speaker.start()

    def _on_submit(self) -> None:
        message = self.input.text().strip()
        if not message:
            return
        self._submit_message(message)

    def _submit_message(self, message: str) -> None:
        self._append("You", message)
        self.input.clear()
        self.input.setEnabled(False)
        self.send_btn.setEnabled(False)

        direct = _local_command(message)
        if direct:
            tool_name, params = direct
            self.state_changed.emit(AgentState.EXECUTING)
            self._worker = DirectToolWorker(self._client, tool_name, params)
            self._worker.finished_ok.connect(self._on_direct_reply)
            self._worker.failed.connect(self._on_error)
            self._worker.start()
            return

        self.state_changed.emit(AgentState.THINKING)
        self._worker = ChatWorker(self._client, message)
        self._worker.finished_ok.connect(self._on_reply)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _on_reply(self, reply: ChatReply) -> None:
        self._append("Nova", reply.reply)
        self._speak(reply.reply)

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
        self.state_changed.emit(AgentState.IDLE)

    def _on_direct_reply(self, result: ToolCallResult) -> None:
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
        self.state_changed.emit(AgentState.IDLE)

    def _on_error(self, error: str) -> None:
        self._append("Nova", f"⚠️ Something went wrong: {error}")
        self._speak("I couldn't complete that request.")
        self.input.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.state_changed.emit(AgentState.IDLE)

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
            self.state_changed.emit(AgentState.EXECUTING)
            confirm_worker = ConfirmWorker(self._client, call.pending_id)
            confirm_worker.finished_ok.connect(
                lambda result: self._append("Nova", result.message or f"{result.tool_name}: {result.result}")
            )
            confirm_worker.failed.connect(lambda err: self._append("Nova", f"⚠️ Confirmation failed: {err}"))
            confirm_worker.finished.connect(lambda: self.state_changed.emit(AgentState.IDLE))
            confirm_worker.start()
            self._confirm_worker = confirm_worker  # keep a reference so it isn't garbage-collected mid-run
        else:
            self._append("Nova", "Okay, I won't do that.")

    def closeEvent(self, event) -> None:  # noqa: N802
        self.stop_listening()
        if self._voice_listener is not None:
            self._voice_listener.wait(2000)
            self._voice_listener = None
        event.accept()
