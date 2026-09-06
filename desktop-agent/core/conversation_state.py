from __future__ import annotations

import time
from enum import Enum

from PySide6.QtCore import QObject, QTimer, Signal


class ConversationState(str, Enum):
    """Matches spec section 36 exactly, plus LOCKED (not in the spec list,
    but needed to visually distinguish 'voice rejected' from ERROR --
    they need different bubble treatment and different recovery: LOCKED
    self-clears back to LISTENING after a beat, ERROR does not)."""

    IDLE = "idle"
    WAKE_DETECTED = "wake_detected"
    VERIFYING = "verifying"
    LOCKED = "locked"
    LISTENING = "listening"
    THINKING = "thinking"
    EXECUTING = "executing"
    SPEAKING = "speaking"
    ACTIVE_CONVERSATION = "active_conversation"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    OFFLINE = "offline"


DEFAULT_INACTIVITY_TIMEOUT_SECONDS = 12.0


class ConversationStateMachine(QObject):
    """
    Central owner of "what is Nova doing right now" (spec section 36).
    Previously this lived nowhere in particular: VoiceListener tracked its
    own armed_until timestamp, ChatPanel emitted ad hoc AgentState values
    on the way to whatever was next, and there was no single place that
    knew whether the assistant was paused/stopped at all. Consequences of
    that: the bubble's Pause/Stop controls didn't actually exist (spec
    section 37), and the old armed_until logic reset itself to 0 after
    exactly one follow-up turn instead of refreshing the window (fixed
    here as a side effect of centralizing the timeout in one place).

    PAUSED and STOPPED are sticky: once set, no other transition is
    accepted until resume()/start() is called explicitly (force=True is
    the only way around this, reserved for pause()/resume()/stop()/
    start()/set_offline() themselves) -- this is what makes "the user can
    directly stop Nova from the bubble" actually true rather than
    advisory: a straggling THINKING->EXECUTING transition from a request
    already in flight when Stop was pressed can't silently reopen it.
    """

    state_changed = Signal(object)  # ConversationState

    def __init__(self, inactivity_timeout: float = DEFAULT_INACTIVITY_TIMEOUT_SECONDS):
        super().__init__()
        self._state = ConversationState.IDLE
        self._paused = False
        self._stopped = False
        self._inactivity_timeout = inactivity_timeout
        self._active_until = 0.0
        self._pre_offline_state: ConversationState | None = None

        # Scheduled precisely against the current session deadline (see
        # _arm_timeout) rather than a fixed-interval poll — a poll cadence
        # coarser than the configured timeout would make the timeout feel
        # inaccurate right at the boundary, and running a perpetual 1Hz
        # timer while nothing is happening has no upside over scheduling
        # exactly when it's needed.
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._check_timeout)

    # ---- thread-safe reads (plain attribute/float comparisons -- safe to
    # call from VoiceListener's own thread without touching Qt's event loop) ----

    @property
    def state(self) -> ConversationState:
        return self._state

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_stopped(self) -> bool:
        return self._stopped

    @property
    def is_active_conversation(self) -> bool:
        """True while a follow-up utterance should be treated as a
        continuation of an already-verified session, without requiring
        the wake word again (spec section 6)."""
        return not self._paused and not self._stopped and time.monotonic() < self._active_until

    # ---- internal transition guard ----

    def _transition(self, new_state: ConversationState, force: bool = False) -> bool:
        if not force and (self._stopped or self._paused):
            return False
        if self._state == new_state:
            return True
        self._state = new_state
        self.state_changed.emit(new_state)
        return True

    def _check_timeout(self) -> None:
        if self._state == ConversationState.ACTIVE_CONVERSATION and time.monotonic() >= self._active_until:
            self._transition(ConversationState.LISTENING)

    def _arm_timeout(self, seconds: float) -> None:
        self._active_until = time.monotonic() + seconds
        self._timeout_timer.start(max(0, int(seconds * 1000)) + 10)  # +10ms margin against float/scheduling jitter

    # ---- voice pipeline events (called from VoiceListener / ChatPanel) ----

    def on_wake_detected(self) -> None:
        self._transition(ConversationState.WAKE_DETECTED)

    def on_verifying(self) -> None:
        self._transition(ConversationState.VERIFYING)

    def on_verified(self, has_immediate_command: bool) -> None:
        self._arm_timeout(self._inactivity_timeout)
        self._transition(ConversationState.THINKING if has_immediate_command else ConversationState.ACTIVE_CONVERSATION)

    def on_rejected(self) -> None:
        self._active_until = 0.0
        self._transition(ConversationState.LOCKED)
        QTimer.singleShot(1200, lambda: self._transition(ConversationState.LISTENING))

    def on_continuation(self) -> None:
        """A follow-up utterance inside an already-active session."""
        self._arm_timeout(self._inactivity_timeout)
        self._transition(ConversationState.THINKING)

    def on_thinking(self) -> None:
        self._transition(ConversationState.THINKING)

    def on_executing(self) -> None:
        self._transition(ConversationState.EXECUTING)

    def on_speaking(self) -> None:
        self._transition(ConversationState.SPEAKING)

    def on_response_complete(self) -> None:
        """Falls back to ACTIVE_CONVERSATION if the session window is
        still open, otherwise LISTENING -- so a fast follow-up doesn't
        visually flicker back to 'idle listening' between turns."""
        self._transition(ConversationState.ACTIVE_CONVERSATION if self.is_active_conversation else ConversationState.LISTENING)

    def on_error(self) -> None:
        self._transition(ConversationState.ERROR)

    # ---- spec section 37: bubble controls ----

    def start(self) -> None:
        self._stopped = False
        self._paused = False
        self._transition(ConversationState.LISTENING, force=True)

    def pause(self) -> None:
        self._paused = True
        self._active_until = 0.0
        self._transition(ConversationState.PAUSED, force=True)

    def resume(self) -> None:
        self._paused = False
        self._transition(ConversationState.LISTENING, force=True)

    def stop(self) -> None:
        self._stopped = True
        self._paused = False
        self._active_until = 0.0
        self._transition(ConversationState.STOPPED, force=True)

    # ---- connectivity ----

    def set_offline(self, offline: bool) -> None:
        if offline and self._state != ConversationState.OFFLINE:
            self._pre_offline_state = self._state
            self._transition(ConversationState.OFFLINE, force=True)
        elif not offline and self._state == ConversationState.OFFLINE:
            restore = self._pre_offline_state or ConversationState.LISTENING
            # Don't silently un-pause/un-stop just because connectivity returned.
            if self._paused:
                restore = ConversationState.PAUSED
            elif self._stopped:
                restore = ConversationState.STOPPED
            self._transition(restore, force=True)
