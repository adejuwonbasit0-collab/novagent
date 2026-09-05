from __future__ import annotations

import asyncio
import sys
import threading

from PySide6.QtWidgets import QApplication

from core.api_client import NovaAPIClient
from core.device_store import DeviceStore
from core.ws_client import DeviceWebSocketClient
from ui.bubble import AgentState, AssistantBubble
from ui.chat_panel import ChatPanel
from ui.onboarding import OnboardingDialog
from config import settings


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

        self.bubble.clicked.connect(self._toggle_chat_panel)
        self.bubble.move(100, 100)

    def _shutdown_threads(self) -> None:
        if self.chat_panel is not None:
            self.chat_panel.stop_listening()
            if self.chat_panel._voice_listener is not None:
                self.chat_panel._voice_listener.wait(2000)
        self.ws_client.stop()

    def _toggle_chat_panel(self) -> None:
        if self.chat_panel is None:
            self.chat_panel = ChatPanel(self.client)
            self.chat_panel.state_changed.connect(self.bubble.set_state)

        if self.chat_panel.isVisible():
            self.chat_panel.hide()
        else:
            self.chat_panel.show()
            self.chat_panel.raise_()
            self.chat_panel.input.setFocus()

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
        self.chat_panel.state_changed.connect(self.bubble.set_state)
        self.chat_panel.start_listening()

        self._start_ws_client()

        self.bubble.set_state(AgentState.IDLE)
        self.bubble.show()
        return self.app.exec()


if __name__ == "__main__":
    sys.exit(NovaAgentApp().run())
