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
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)  # closing the chat panel shouldn't kill the tray bubble
        self.app.aboutToQuit.connect(self._shutdown_threads)

        self.client = NovaAPIClient()
        self.bubble = AssistantBubble()
        self.chat_panel: ChatPanel | None = None

        self.ws_client = DeviceWebSocketClient()
        self._ws_thread: threading.Thread | None = None
        self._health_worker: HealthCheckWorker | None = None
        self._health_timer = QTimer()
        self._health_timer.setInterval(HEALTH_CHECK_INTERVAL_MS)
        self._health_timer.timeout.connect(self._run_health_check)

        self.reminder_scheduler = ReminderScheduler(self.client)
        self.reminder_scheduler.reminder_due.connect(self._on_reminder_due)

        self.bubble.clicked.connect(self._toggle_chat_panel)
        self.bubble.move(100, 100)

    def _shutdown_threads(self) -> None:
        if self.chat_panel is not None:
            self.chat_panel.stop_listening()
            if self.chat_panel._voice_listener is not None:
                # Same reasoning as chat_panel.py's _toggle_voice: sd.rec()
                # can block up to 5s, so this needs real margin, not the
                # 2000ms this used to use — a timeout here previously just
                # let the app quit anyway, which destroys the QThread
                # object while the OS thread could still be running.
                self.chat_panel._voice_listener.wait(6000)
            if self.chat_panel._sync_worker.isRunning():
                self.chat_panel._sync_worker.wait(3000)
            self.chat_panel._speech.shutdown()
        if self._health_worker is not None and self._health_worker.isRunning():
            self._health_worker.wait(3000)
        self.reminder_scheduler.stop()
        self.ws_client.stop()

    def _toggle_chat_panel(self) -> None:
        if self.chat_panel is None:
            self.chat_panel = ChatPanel(self.client)
            self.chat_panel.fsm.state_changed.connect(self.bubble.set_state)
            self._wire_bubble_controls()

        if self.chat_panel.isVisible():
            self.chat_panel.hide()
        else:
            self.chat_panel.show()
            self.chat_panel.raise_()
            self.chat_panel.input.setFocus()

    def _wire_bubble_controls(self) -> None:
        """Spec section 37: the bubble's own Pause/Resume/Stop menu
        controls the same ConversationStateMachine everything else reacts
        to -- VoiceListener already checks fsm.is_paused/is_stopped every
        loop iteration, so these take effect within one recording cycle
        without needing to reach into the listener thread directly."""
        self.bubble.pause_requested.connect(self.chat_panel.fsm.pause)
        self.bubble.resume_requested.connect(self.chat_panel.fsm.start)
        self.bubble.stop_requested.connect(self.chat_panel.fsm.stop)

    def _run_onboarding_if_needed(self) -> bool:
        if DeviceStore.is_registered():
            return True

        dialog = OnboardingDialog(self.client)
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
        if self.chat_panel is not None:
            self.chat_panel.fsm.set_offline(not reachable)
        else:
            self.bubble.set_state(ConversationState.OFFLINE if not reachable else ConversationState.IDLE)

    def _on_reminder_due(self, reminder) -> None:
        # self.chat_panel always exists by the time reminders can fire —
        # run() creates it (and starts listening) before starting the
        # scheduler below — but guard anyway since this is reachable from
        # a QTimer callback outside the normal call stack.
        if self.chat_panel is None:
            return
        present_reminder(reminder, self.client, self.chat_panel._speech)

    def run(self) -> int:
        if not self._run_onboarding_if_needed():
            return 0  # user closed the login dialog without completing it

        try:
            settings.ASSISTANT_NAME = asyncio.run(self.client.get_assistant_name())
        except Exception:
            pass

        # Keep the listener alive with the agent, not with the optional chat
        # window. The user can still stop it from the panel when needed.
        self.chat_panel = ChatPanel(self.client)
        self.chat_panel.fsm.state_changed.connect(self.bubble.set_state)
        self._wire_bubble_controls()
        self.chat_panel.start_listening()

        self._start_ws_client()
        self._health_timer.start()
        self._run_health_check()  # don't wait a full interval for the first reading
        self.reminder_scheduler.start()

        self.bubble.set_state(ConversationState.IDLE)
        self.bubble.show()
        return self.app.exec()


if __name__ == "__main__":
    sys.exit(NovaAgentApp().run())
