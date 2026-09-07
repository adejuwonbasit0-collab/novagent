from __future__ import annotations

import asyncio
import sys
import threading

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication

from core.api_client import NovaAPIClient
from core.conversation_state import ConversationState
from core.device_store import DeviceStore
from core.reminder_scheduler import ReminderScheduler
from core.voice_service import VoiceService
from core.ws_client import DeviceWebSocketClient
from ui.bubble import AssistantBubble
from ui.chat_panel import ChatPanel
from ui.onboarding import OnboardingDialog
from ui.reminder_alert import present_reminder
from config import settings

HEALTH_CHECK_INTERVAL_MS = 15000


class HealthCheckWorker(QThread):
    """One-shot connectivity probe, fired on a timer rather than kept as a
    persistent thread -- OFFLINE (spec section 36/38) needs to reflect
    actual reachability, not just 'the WebSocket happens to be connected
    right now', so this hits the same REST endpoint any other request
    would use."""

    result = Signal(bool)

    def __init__(self, client: NovaAPIClient):
        super().__init__()
        self._client = client

    def run(self) -> None:
        ok = asyncio.run(self._client.health_check())
        self.result.emit(ok)


class NovaAgentApp:
    """
    Spec section 9's architecture, applied: VoiceService (fsm, speaker
    verification, VoiceListener, SpeechManager) is constructed here and
    lives for the whole process, independent of any UI window. ChatPanel
    only ever *observes/drives* VoiceService -- it never owns any of
    that -- so closing/hiding it can't affect the pipeline (see
    ChatPanel.closeEvent).

    ChatPanel is still constructed eagerly here, just never shown until
    the bubble is clicked -- it has to exist for its
    voice_service.transcript connection to be live, since that's what
    actually turns a recognized utterance into a tool call or a chat
    request (route_locally / ChatWorker / DirectToolWorker all live on
    ChatPanel). A version of this that created ChatPanel lazily on first
    bubble click would leave every voice command going nowhere until the
    user opened the window at least once -- worse than the "chat panel
    owns critical services" problem this refactor set out to fix.
    """

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)  # closing the chat panel shouldn't kill the tray bubble
        self.app.aboutToQuit.connect(self._shutdown)

        self.client = NovaAPIClient()
        self.voice_service = VoiceService(self.client)
        self.voice_service.fsm.state_changed.connect(self._on_fsm_state_changed)

        self.bubble = AssistantBubble()
        # Created now, shown later (see class docstring) -- this is what
        # actually turns a voice transcript into a tool call/chat
        # request, so it must be alive for the whole process, not just
        # while the window happens to be visible.
        self.chat_panel = ChatPanel(self.client, self.voice_service)

        self.ws_client = DeviceWebSocketClient()
        self._ws_thread: threading.Thread | None = None
        self._health_worker: HealthCheckWorker | None = None
        self._health_timer = QTimer()
        self._health_timer.setInterval(HEALTH_CHECK_INTERVAL_MS)
        self._health_timer.timeout.connect(self._run_health_check)

        self.reminder_scheduler = ReminderScheduler(self.client)
        self.reminder_scheduler.reminder_due.connect(self._on_reminder_due)

        self.bubble.clicked.connect(self._toggle_chat_panel)
        self.bubble.pause_requested.connect(self.voice_service.fsm.pause)
        self.bubble.resume_requested.connect(self.voice_service.fsm.start)
        self.bubble.stop_requested.connect(self.voice_service.fsm.stop)
        self.bubble.move(100, 100)

    def _on_fsm_state_changed(self, state: ConversationState) -> None:
        self.bubble.set_state(state)

    def _shutdown(self) -> None:
        """Spec section 18's shutdown order. Every step below either has
        a real wait()/timeout or delegates to something that does
        (VoiceService.shutdown mirrors this same rule internally) --
        nothing here drops a QThread reference without confirming it
        actually finished first."""
        self.voice_service.shutdown()  # stop wake listener -> stop TTS -> wait
        if self._health_worker is not None and self._health_worker.isRunning():
            self._health_worker.wait(3000)  # stop network workers
        self.reminder_scheduler.stop()  # stop reminder service
        self.ws_client.stop()  # stop websocket

    def _toggle_chat_panel(self) -> None:
        if self.chat_panel.isVisible():
            self.chat_panel.hide()
        else:
            self.chat_panel.show()
            # raise_()/activateWindow() -- not just show() -- so the panel
            # actually comes to the front instead of appearing behind
            # whatever else has focus (a real report against the old
            # code: the window could open "behind" other applications
            # with no obvious way to bring it forward).
            self.chat_panel.raise_()
            self.chat_panel.activateWindow()
            self.chat_panel.input.setFocus()

    def _run_onboarding_if_needed(self) -> bool:
        if DeviceStore.is_registered():
            return True

        dialog = OnboardingDialog(self.client)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog.exec() == dialog.DialogCode.Accepted

    def _start_ws_client(self) -> None:
        """
        Runs the WebSocket listener in its own thread with its own asyncio
        event loop — PySide6's event loop and asyncio don't share one, so
        this keeps the OS-command channel alive independent of whatever
        the Qt UI thread is doing (including while a modal dialog is open).
        """

        def _thread_main():
            asyncio.run(self.ws_client.run_forever())

        self._ws_thread = threading.Thread(target=_thread_main, daemon=True)
        self._ws_thread.start()

    def _run_health_check(self) -> None:
        if self._health_worker is not None and self._health_worker.isRunning():
            return  # previous probe still in flight -- skip this tick rather than piling up workers
        self._health_worker = HealthCheckWorker(self.client)
        self._health_worker.result.connect(self._on_health_result)
        self._health_worker.start()

    def _on_health_result(self, reachable: bool) -> None:
        # fsm lives on VoiceService now, independent of whether the chat
        # panel has ever been opened -- no None-check needed.
        self.voice_service.fsm.set_offline(not reachable)

    def _on_reminder_due(self, reminder) -> None:
        present_reminder(reminder, self.client, self.voice_service)

    def run(self) -> int:
        if not self._run_onboarding_if_needed():
            return 0  # user closed the login dialog without completing it

        try:
            settings.ASSISTANT_NAME = asyncio.run(self.client.get_assistant_name())
        except Exception:
            pass

        # Controlled startup sequence (spec section 4): sync the speaker
        # profile, THEN arm the microphone/wake-word pipeline, THEN (once
        # VoiceListener confirms it's actually listening) speak the
        # greeting -- see VoiceService.start(). No chat window is
        # required for any of this.
        self.voice_service.start()

        self._start_ws_client()
        self._health_timer.start()
        self._run_health_check()  # don't wait a full interval for the first reading
        self.reminder_scheduler.start()

        self.bubble.set_state(ConversationState.IDLE)
        self.bubble.show()
        return self.app.exec()


if __name__ == "__main__":
    sys.exit(NovaAgentApp().run())
