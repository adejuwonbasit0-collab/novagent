from __future__ import annotations

"""
Local reminder/alarm scheduling (spec sections 34, 35, 38).

Before this module, "create a reminder" only ever inserted a row in the
backend's Postgres database (see backend/app/tools/reminder_tools.py and
backend/app/api/v1/reminders.py — both are real, correctly built, and
already expose everything needed: list/get/patch/snooze/delete, a
notify_desktop/notify_sound flag per reminder, timezone handling). But
nothing anywhere ever turned "a row exists with due_at in the past" into an
actual alarm — no notification, no sound, no snooze/dismiss prompt. Section
35's whole point ("Nova should work as an alarm... at 6 AM: sound alarm,
show notification, assistant activates, user can snooze, user can dismiss")
had no implementation at all. This module is that missing piece.

Design:
- Polls GET /api/v1/reminders periodically (default 60s) and schedules a
  QTimer for each pending/snoozed reminder due within the lookahead window.
  Polling (rather than only scheduling once at startup) is what picks up
  reminders created *after* the agent started, and what recovers gracefully
  from the process having been asleep/suspended past a reminder's due time.
- Per spec section 38 ("time-critical alarms should be locally scheduled"):
  once a QTimer is armed for a specific reminder, firing it needs no
  network call at all — only the periodic re-poll needs connectivity, and
  a poll failure (offline) just means the schedule doesn't pick up brand
  new reminders until connectivity returns; anything already scheduled
  still fires on time.
- Deliberately does NOT attempt recurrence (recurrence_type/recurrence_rule
  are stored on the model but nothing computes "what's the next occurrence
  after this one fires" anywhere in the backend either — that's a real,
  separate gap, not something to half-implement here). One-time reminders
  and manual snoozes work correctly; a "daily" reminder will fire once and
  not reschedule itself. Flagging this explicitly rather than silently
  shipping recurrence that looks supported but isn't (spec section 47).
"""

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from core.api_client import NovaAPIClient

POLL_INTERVAL_MS = 60_000
LOOKAHEAD_SECONDS = 6 * 60 * 60  # only arm timers for reminders due within 6h; re-poll picks up the rest
MAX_TIMER_MS = 2_147_483_647  # Qt's QTimer takes a 32-bit int; anything longer needs re-arming after a poll


@dataclass
class DueReminder:
    id: str
    title: str
    notes: str | None
    notify_desktop: bool
    notify_sound: bool


def _parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class _PollWorker(QThread):
    """
    One-shot background fetch, same pattern as main.py's HealthCheckWorker
    and ui/chat_panel.py's ChatWorker: `asyncio.run()` blocks whatever
    thread calls it for the duration of the HTTP request, so it must never
    run directly on a QTimer.timeout callback (that callback runs on the
    Qt main/UI thread) — doing so would freeze the whole UI, including the
    floating bubble, for up to the request's timeout on every single poll.
    """

    finished_ok = Signal(list)
    failed = Signal()

    def __init__(self, client: NovaAPIClient):
        super().__init__()
        self._client = client

    def run(self) -> None:
        import asyncio

        try:
            reminders = asyncio.run(self._client.get_reminders())
            self.finished_ok.emit(reminders)
        except Exception:
            self.failed.emit()


class ReminderScheduler(QObject):
    """Owns the set of locally-armed reminder timers. UI-agnostic on
    purpose (mirrors VoiceListener/SpeakerVerifier's separation) — this
    only decides *when* a reminder is due; ui/reminder_alert.py decides
    what that looks/sounds like."""

    reminder_due = Signal(object)  # DueReminder

    def __init__(self, client: NovaAPIClient):
        super().__init__()
        self._client = client
        self._armed: dict[str, QTimer] = {}
        self._fired: set[str] = set()  # avoid double-firing on the next poll before the backend status update lands
        self._poll_worker: _PollWorker | None = None

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll)

    def start(self) -> None:
        self._poll_timer.start()
        QTimer.singleShot(0, self._poll)  # first poll immediately, don't wait a full interval

    def stop(self) -> None:
        self._poll_timer.stop()
        if self._poll_worker is not None:
            self._poll_worker.wait(3000)
        for timer in self._armed.values():
            timer.stop()
        self._armed.clear()

    def _poll(self) -> None:
        if self._poll_worker is not None and self._poll_worker.isRunning():
            return  # a poll is already in flight — don't stack another one on a slow backend

        self._poll_worker = _PollWorker(self._client)
        self._poll_worker.finished_ok.connect(self._on_poll_result)
        self._poll_worker.start()

    def _on_poll_result(self, reminders: list) -> None:
        now = time.time()
        seen_ids: set[str] = set()

        for r in reminders:
            status = r.get("status")
            if status not in ("pending", "snoozed"):
                continue

            reminder_id = r["id"]
            seen_ids.add(reminder_id)

            if reminder_id in self._fired or reminder_id in self._armed:
                continue  # already handled or already scheduled — don't re-arm

            due_str = r.get("snoozed_until") if status == "snoozed" else r.get("due_at")
            if not due_str:
                continue

            due_epoch = _parse_utc(due_str).timestamp()
            delay_seconds = due_epoch - now

            if delay_seconds > LOOKAHEAD_SECONDS:
                continue  # too far out — next poll (or one after) will pick it up as it gets closer

            self._arm(
                DueReminder(
                    id=reminder_id,
                    title=r.get("title", "Reminder"),
                    notes=r.get("notes"),
                    notify_desktop=r.get("notify_desktop", True),
                    notify_sound=r.get("notify_sound", True),
                ),
                max(0.0, delay_seconds),
            )

        # A reminder that disappeared from the list (completed/dismissed/
        # deleted from elsewhere — e.g. the web dashboard) shouldn't still
        # fire locally just because it was armed before that happened.
        for stale_id in list(self._armed):
            if stale_id not in seen_ids:
                self._armed.pop(stale_id).stop()

    def _arm(self, reminder: DueReminder, delay_seconds: float) -> None:
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._fire(reminder))
        timer.start(min(int(delay_seconds * 1000), MAX_TIMER_MS))
        self._armed[reminder.id] = timer

    def _fire(self, reminder: DueReminder) -> None:
        self._armed.pop(reminder.id, None)
        self._fired.add(reminder.id)
        self.reminder_due.emit(reminder)
