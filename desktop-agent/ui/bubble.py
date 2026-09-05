from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from config import settings


class AgentState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    EXECUTING = "executing"
    DONE = "done"


_STATE_COLORS = {
    AgentState.IDLE: QColor("#6366f1"),
    AgentState.LISTENING: QColor("#22c55e"),
    AgentState.THINKING: QColor("#f59e0b"),
    AgentState.EXECUTING: QColor("#3b82f6"),
    AgentState.DONE: QColor("#22c55e"),
}


class AssistantBubble(QWidget):
    """
    The always-on-top floating bubble described in spec section 4: small,
    draggable, shows the current pipeline state visually, click opens the
    chat panel. Kept intentionally minimal — no external image assets, an
    animated ring drawn in code so the whole thing renders correctly with
    zero setup.
    """

    clicked = Signal()

    def __init__(self, size: int = settings.BUBBLE_SIZE):
        super().__init__()
        self._size = size
        self._state = AgentState.IDLE
        self._drag_offset: QPoint | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # excludes it from the taskbar, per "small, elegant, unobtrusive"
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(size, size)

    def set_state(self, state: AgentState) -> None:
        self._state = state
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt override signature
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = _STATE_COLORS[self._state]
        margin = 4

        # Outer ring — pulses conceptually via state color; actual animation
        # (opacity/scale) is a follow-up once this is running against a real display.
        pen = QPen(color, 3)
        painter.setPen(pen)
        painter.setBrush(QColor(30, 30, 35, 235))
        painter.drawEllipse(margin, margin, self._size - 2 * margin, self._size - 2 * margin)

        # Center dot indicates "active" vs idle at a glance
        if self._state != AgentState.IDLE:
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            dot = self._size // 6
            center = self._size // 2
            painter.drawEllipse(center - dot // 2, center - dot // 2, dot, dot)

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
