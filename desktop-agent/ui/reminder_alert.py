from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from core.api_client import APIError, NovaAPIClient
from core.reminder_scheduler import DueReminder
from core.voice_service import VoiceService
from os_control.base import get_controller


class _ReminderActionWorker(QThread):
    """Fire-and-forget snooze/dismiss call — same reasoning as every other
    network call in this app: never block the Qt thread showing the alert
    dialog, and never let this object be dropped while still running (see
    main.py's _pending_action_workers list below)."""

    failed = Signal(str)

    def __init__(self, coro_factory):
        super().__init__()
        self._coro_factory = coro_factory

    def run(self) -> None:
        import asyncio

        try:
            asyncio.run(self._coro_factory())
        except APIError as e:
            self.failed.emit(e.detail)
        except Exception as e:
            self.failed.emit(str(e))


_pending_action_workers: list[_ReminderActionWorker] = []


def present_reminder(reminder: DueReminder, client: NovaAPIClient, voice_service: VoiceService) -> None:
    """
    The actual alarm moment (spec section 35): notification + sound + Nova
    speaking the reminder aloud + a real Snooze/Dismiss dialog — not just a
    silent database status flip. Called on the Qt main thread from
    ReminderScheduler.reminder_due.

    Speech goes through the shared VoiceService (the same one the chat
    panel and the wake-word pipeline use) rather than a standalone
    SpeechSpeaker of its own. Two independent pyttsx3 engines speaking at
    the same time — Nova mid-reply to something the user just asked, and
    a reminder firing at that exact moment — would talk over each other.
    Routing both through one queue means a reminder that fires mid-
    conversation waits its turn instead of colliding.
    """
    title = "Nova reminder"
    body = reminder.title + (f" — {reminder.notes}" if reminder.notes else "")

    if reminder.notify_desktop:
        # Local OS notification — no network involved, matches spec section
        # 38's offline requirement. Best-effort: a notification failure
        # (e.g. no notification daemon on a minimal Linux setup) shouldn't
        # block the rest of the alarm (sound, speech, dialog).
        try:
            get_controller().send_notification(title, body)
        except Exception:
            pass

    if reminder.notify_sound:
        # A real, always-available alarm sound with zero asset files to
        # ship or licenses to track — QApplication.beep() is a genuine
        # system beep, not a placeholder. Repeated 3x with a short gap so
        # it's actually noticeable, closer to "alarm" than "single blip".
        for i in range(3):
            QTimer.singleShot(i * 400, QApplication.beep)

    voice_service.speak(f"Reminder: {reminder.title}")
    # Intentionally not awaited — TTS speaks in the background (or queues
    # behind whatever Nova's already saying) while the dialog below is
    # already interactive; the user shouldn't have to wait for the
    # sentence to finish before Snooze/Dismiss are clickable.

    box = QMessageBox()
    box.setWindowTitle(title)
    box.setText(body)
    snooze_btn = box.addButton("Snooze 5 min", QMessageBox.ButtonRole.ActionRole)
    dismiss_btn = box.addButton("Dismiss", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(dismiss_btn)
    box.exec()

    if box.clickedButton() is snooze_btn:
        worker = _ReminderActionWorker(lambda: client.snooze_reminder(reminder.id, 5))
    else:
        worker = _ReminderActionWorker(lambda: client.dismiss_reminder(reminder.id))

    # Kept alive in a module-level list rather than left to fall out of
    # scope when this function returns — a QThread whose Python wrapper
    # gets garbage collected while still running is exactly the crash class
    # fixed elsewhere in this codebase (see SpeechManager's docstring and
    # batch 5's chat_panel.py fixes): "QThread: Destroyed while thread is
    # still running."
    _pending_action_workers.append(worker)
    worker.finished.connect(lambda: _pending_action_workers.remove(worker) if worker in _pending_action_workers else None)
    worker.start()
