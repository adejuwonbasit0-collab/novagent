from __future__ import annotations

import socket

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.api_client import APIError, NovaAPIClient
from core.device_store import detect_platform


class LoginWorker(QThread):
    finished_ok = Signal()
    failed = Signal(str)

    def __init__(self, client: NovaAPIClient, email: str, password: str):
        super().__init__()
        self._client = client
        self._email = email
        self._password = password

    def run(self) -> None:
        import asyncio

        async def do_login():
            await self._client.login(self._email, self._password)
            await self._client.register_this_device(f"{socket.gethostname()} ({detect_platform()})")

        try:
            asyncio.run(do_login())
            self.finished_ok.emit()
        except APIError as e:
            self.failed.emit(e.detail)
        except Exception as e:
            self.failed.emit(str(e))


class OnboardingDialog(QDialog):
    """
    First-run flow: login with the account created on the web dashboard,
    then register this machine as a device (spec section 32, steps 2-4).
    Registration produces a device token that all subsequent app launches
    use — this dialog only ever appears once per machine, unless the
    device is later revoked/deleted from device_store.
    """

    def __init__(self, client: NovaAPIClient):
        super().__init__()
        self._client = client
        self.setWindowTitle("Sign in to Nova")
        self.resize(320, 200)

        # BUG FIX: this dialog is launched at process startup from a
        # background/tray-ish launch path (double-clicking main.py, a
        # shortcut, a startup entry) rather than from a click inside an
        # already-focused window. On Windows in particular that means the
        # new window frequently does NOT get foreground focus (the OS's
        # foreground-lock behavior) -- it opens truthfully but behind
        # whatever the user was already looking at, with nothing on
        # screen indicating it's there. That's the "it hid behind so I
        # can't set up" report: the dialog existed and was even modal
        # (blocking main.py's startup), but invisible behind other
        # windows, so it looked like setup silently did nothing. Force it
        # on top for its (short, first-run-only) lifetime and explicitly
        # pull focus once shown.
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Sign in with your Nova account:"))

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Email")
        layout.addWidget(self.email_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_input)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.login_btn = QPushButton("Sign in & connect this device")
        self.login_btn.clicked.connect(self._on_submit)
        layout.addWidget(self.login_btn)

        self._worker: LoginWorker | None = None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # raise_()/activateWindow() in addition to the always-on-top flag
        # above -- on-top alone can still leave a window unfocused (visible
        # but not receiving keyboard input) on some window managers. Both
        # together is what actually guarantees the user sees AND can type
        # into it the moment it appears.
        self.raise_()
        self.activateWindow()

    def _on_submit(self) -> None:
        email = self.email_input.text().strip()
        password = self.password_input.text()
        if not email or not password:
            self.status_label.setText("Enter both email and password.")
            return

        self.login_btn.setEnabled(False)
        self.status_label.setText("Connecting…")

        self._worker = LoginWorker(self._client, email, password)
        self._worker.finished_ok.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    def _on_success(self) -> None:
        self.accept()

    def _on_failure(self, detail: str) -> None:
        self.login_btn.setEnabled(True)
        self.status_label.setText("")
        QMessageBox.warning(self, "Sign-in failed", detail)
