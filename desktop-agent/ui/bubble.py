from __future__ import annotations

import math

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from config import settings
from core.conversation_state import ConversationState

_STATE_COLORS = {
    ConversationState.IDLE: QColor("#6366f1"),
    ConversationState.LISTENING: QColor("#6366f1"),
    ConversationState.WAKE_DETECTED: QColor("#22c55e"),
    ConversationState.VERIFYING: QColor("#22c55e"),
    ConversationState.LOCKED: QColor("#ef4444"),
    ConversationState.THINKING: QColor("#f59e0b"),
    ConversationState.EXECUTING: QColor("#3b82f6"),
    ConversationState.SPEAKING: QColor("#38bdf8"),
    ConversationState.ACTIVE_CONVERSATION: QColor("#22c55e"),
    ConversationState.PAUSED: QColor("#9ca3af"),
    ConversationState.STOPPED: QColor("#6b7280"),
    ConversationState.ERROR: QColor("#ef4444"),
    ConversationState.OFFLINE: QColor("#78716c"),
}

# States whose visual is an animated soundwave -- the "Nova heard/is
# producing speech" moment (spec: "there should be a sign it wakes").
_SOUNDWAVE_STATES = (ConversationState.WAKE_DETECTED, ConversationState.VERIFYING, ConversationState.SPEAKING)
# A slower breathing pulse -- distinguishes "session open, listening for
# a follow-up with no wake word needed" from the static idle ring.
_BREATHING_STATES = (ConversationState.ACTIVE_CONVERSATION,)

_ANIMATION_INTERVAL_MS = 40
_BAR_COUNT = 5


class AssistantBubble(QWidget):
    """
    The always-on-top floating bubble described in spec section 4: small,
    draggable, shows the current pipeline state (ConversationState --
    core/conversation_state.py) visually, click opens the chat panel,
    right-click opens Pause/Resume/Stop controls (spec section 37 -- the
    user should be able to control Nova directly from here, without going
    back to the website for routine pause/stop).

    The soundwave animation (WAKE_DETECTED/VERIFYING/SPEAKING) starts the
    instant a wake phrase is heard, independent of whether verification
    ends up passing -- immediate visual confirmation that Nova heard
    something, before the (fast, but non-zero) verification result comes
    back as either a transition onward or a brief LOCKED flash.
    """

    clicked = Signal()
    pause_requested = Signal()
    resume_requested = Signal()
    stop_requested = Signal()

    def __init__(self, size: int = settings.BUBBLE_SIZE):
        super().__init__()
        self._size = size
        self._state = ConversationState.IDLE
        self._drag_offset: QPoint | None = None
        self._anim_phase = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(_ANIMATION_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # excludes it from the taskbar, per "small, elegant, unobtrusive"
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(size, size)
        self.setToolTip("Nova — left-click to open, right-click for controls")

    def set_state(self, state: ConversationState) -> None:
        self._state = state
        if state in _SOUNDWAVE_STATES or state in _BREATHING_STATES:
            if not self._timer.isActive():
                self._anim_phase = 0.0
                self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _on_tick(self) -> None:
        self._anim_phase += 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = _STATE_COLORS[self._state]
        margin = 4

        pen = QPen(color, 3)
        painter.setPen(pen)
        painter.setBrush(QColor(30, 30, 35, 235))
        painter.drawEllipse(margin, margin, self._size - 2 * margin, self._size - 2 * margin)

        if self._state in _SOUNDWAVE_STATES:
            self._paint_soundwave(painter, color)
        elif self._state in _BREATHING_STATES:
            self._paint_breathing_ring(painter, color, margin)
        elif self._state == ConversationState.LOCKED:
            self._paint_locked(painter, color)
        elif self._state == ConversationState.PAUSED:
            self._paint_paused(painter, color)
        elif self._state == ConversationState.STOPPED:
            self._paint_stopped(painter, color)
        elif self._state == ConversationState.ERROR:
            self._paint_error(painter, color)
        elif self._state == ConversationState.OFFLINE:
            self._paint_offline(painter, color)
        elif self._state not in (ConversationState.IDLE, ConversationState.LISTENING):
            # THINKING / EXECUTING -- simple "active" dot, unchanged from
            # the original design.
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            dot = self._size // 6
            center = self._size // 2
            painter.drawEllipse(center - dot // 2, center - dot // 2, dot, dot)

    def _paint_soundwave(self, painter: QPainter, color: QColor) -> None:
        """Siri-style vertical bars, each on its own phase offset so they
        pulse independently rather than moving in lockstep -- reads as
        'actively listening/processing speech' rather than a generic spinner."""
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)

        usable_width = self._size * 0.55
        bar_width = usable_width / (_BAR_COUNT * 1.6)
        gap = bar_width * 0.6
        total_width = _BAR_COUNT * bar_width + (_BAR_COUNT - 1) * gap
        start_x = (self._size - total_width) / 2
        center_y = self._size / 2
        max_half_height = self._size * 0.26

        for i in range(_BAR_COUNT):
            phase = self._anim_phase * 0.35 + i * 1.1
            amplitude = 0.35 + 0.65 * abs(math.sin(phase))
            half_height = max(2.0, max_half_height * amplitude)
            x = start_x + i * (bar_width + gap)
            painter.drawRoundedRect(
                x, center_y - half_height, bar_width, half_height * 2, bar_width / 2, bar_width / 2
            )

    def _paint_breathing_ring(self, painter: QPainter, color: QColor, margin: float) -> None:
        """Slow scale pulse on an inner ring -- calmer than the soundwave,
        signals 'still listening, no wake word needed' during an open
        session rather than 'just heard/producing speech'."""
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        scale = 0.5 + 0.5 * (0.5 + 0.5 * math.sin(self._anim_phase * 0.12))
        inner_margin = margin + (self._size * 0.18) * (1.0 - scale)
        pen = QPen(color, 2)
        painter.setPen(pen)
        painter.drawEllipse(inner_margin, inner_margin, self._size - 2 * inner_margin, self._size - 2 * inner_margin)

    def _paint_locked(self, painter: QPainter, color: QColor) -> None:
        """A no-entry glyph -- deliberately distinct from every other
        state so 'voice not recognized' can never be mistaken for
        'thinking' or 'executing' at a glance."""
        painter.setPen(QPen(color, 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r = self._size * 0.22
        center = self._size / 2
        painter.drawEllipse(center - r, center - r, r * 2, r * 2)
        offset = r * 0.7
        painter.drawLine(center - offset, center - offset, center + offset, center + offset)

    def _paint_paused(self, painter: QPainter, color: QColor) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        bar_w = self._size * 0.09
        bar_h = self._size * 0.28
        center = self._size / 2
        gap = bar_w * 0.9
        painter.drawRoundedRect(center - gap - bar_w, center - bar_h / 2, bar_w, bar_h, bar_w / 3, bar_w / 3)
        painter.drawRoundedRect(center + gap, center - bar_h / 2, bar_w, bar_h, bar_w / 3, bar_w / 3)

    def _paint_stopped(self, painter: QPainter, color: QColor) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        side = self._size * 0.22
        center = self._size / 2
        painter.drawRoundedRect(center - side / 2, center - side / 2, side, side, side * 0.15, side * 0.15)

    def _paint_error(self, painter: QPainter, color: QColor) -> None:
        painter.setPen(QPen(color, 3))
        center = self._size / 2
        half = self._size * 0.14
        painter.drawLine(center, center - half, center, center + half * 0.2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        dot_r = self._size * 0.025
        painter.drawEllipse(center - dot_r, center + half * 0.55, dot_r * 2, dot_r * 2)

    def _paint_offline(self, painter: QPainter, color: QColor) -> None:
        """Faded ring already communicates 'not the normal active state';
        adds a diagonal slash so it isn't confused with PAUSED at a glance."""
        painter.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
        r = self._size * 0.2
        center = self._size / 2
        painter.drawEllipse(center - r, center - r, r * 2, r * 2)

    # ---- controls (spec section 37) ----

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        if self._state == ConversationState.PAUSED:
            menu.addAction("Resume", self.resume_requested.emit)
        elif self._state != ConversationState.STOPPED:
            menu.addAction("Pause", self.pause_requested.emit)
        else:
            menu.addAction("Start", self.resume_requested.emit)

        if self._state != ConversationState.STOPPED:
            menu.addAction("Stop", self.stop_requested.emit)

        menu.addSeparator()
        menu.addAction("Open Nova", self.clicked.emit)
        menu.exec(event.globalPos())

    # ---- dragging ----

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        moved = self._drag_offset is not None and event.globalPosition().toPoint() - self._drag_offset != self.pos()
        self._drag_offset = None
        if not moved:
            self.clicked.emit()
