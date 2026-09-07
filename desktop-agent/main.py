from __future__ import annotations

import asyncio
import logging
import sys
import threading

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication

from core.api_client import NovaAPIClient
from core.conversation_state import ConversationState
from core.device_store import DeviceStore
from core.reminder_scheduler import ReminderScheduler
from core.thread_safety import log_thread_event, stop_and_release
from core.ws_client import DeviceWebSocketClient
from ui.bubble import AssistantBubble
from ui.chat_panel import ChatPanel
from ui.onboarding import OnboardingDialog
from ui.reminder_alert import present_reminder
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("nova.threads")

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
        log_thread_event("STARTED", self)
        ok = asyncio.run(self._client.health_check())
        self.result.emit(ok)
        log_thread_event("STOPPED", self)


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
        # Explicit, ordered shutdown (per the requested shutdown sequence):
        # stop the things that generate new work first (voice, reminders,
        # websocket), then wait for whatever's already in flight to
        # actually finish, and only then let QApplication exit. Every
        # QThread stop goes through stop_and_release so none of them can
        # be dropped while still running -- see core/thread_safety.py.
        if self.chat_panel is not None:
            self.chat_panel.stop_listening()
            listener = self.chat_panel._voice_listener
            if listener is not None:
                stop_and_release(listener, listener.stop, 6000, lambda: setattr(self.chat_panel, "_voice_listener", None))
            if self.chat_panel._sync_worker.isRunning():
                self.chat_panel._sync_worker.wait(3000)
            self.chat_panel._speech.shutdown()
        if self._health_worker is not None and self._health_worker.isRunning():
            self._health_worker.wait(3000)
        self.reminder_scheduler.stop()
        self.ws_client.stop()
        logger.info("[THREAD] Shutdown sequence complete")

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

        self.bubble.set_state(ConversationState.IDLE)
        self.bubble.show()

        # Deferred to fire on the FIRST iteration of the Qt event loop, not
        # before app.exec() below has even started it. ChatPanel's own
        # constructor starts a QThread (SpeakerSyncWorker), and
        # start_listening() below starts another (VoiceListener) plus
        # queues onto a third (the persistent SpeechWorker inside
        # SpeechManager, itself also created in ChatPanel.__init__) --
        # every one of them communicates back to the GUI thread via queued
        # signals, and a queued signal only gets delivered once the
        # receiving thread's event loop is actually pumping. Constructing
        # ChatPanel (and therefore starting these threads) before exec()
        # begins doesn't crash by itself, but it means their very first
        # signals queue up with no guarantee of *when* the loop first gets
        # around to them, relative to whatever else this call stack is
        # still doing. Deferring the whole thing removes that ambiguity.
        QTimer.singleShot(0, self._start_background_services)

        return self.app.exec()

    def _start_background_services(self) -> None:
        # Guarded: on the vanishingly small chance the user clicks the
        # bubble before this deferred call fires, _toggle_chat_panel will
        # already have created self.chat_panel. Recreating it here would
        # replace that reference while ITS OWN background threads (the
        # SpeakerSyncWorker + persistent SpeechWorker started inside
        # ChatPanel.__init__) could still be running -- the exact bug
        # class this whole file is about avoiding.
        if self.chat_panel is None:
            self.chat_panel = ChatPanel(self.client)
            self.chat_panel.fsm.state_changed.connect(self.bubble.set_state)
            self._wire_bubble_controls()
        self.chat_panel.start_listening()

        self._start_ws_client()
        self._health_timer.start()
        self._run_health_check()  # don't wait a full interval for the first reading
        self.reminder_scheduler.start()


if __name__ == "__main__":
    sys.exit(NovaAgentApp().run())
