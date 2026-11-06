# studyguard/ui/widgets/timeline.py
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from studyguard.core.events import AppEvent


EVENT_ICONS = {
    "SESSION_START": "▶",
    "SESSION_END": "■",
    "PHONE_DETECTED": "📱",
    "LOOKING_AWAY": "◉",
    "DROWSINESS": "⚠",
    "EXCESSIVE_BLINKING": "◌",
    "YAWN": "◒",
    "BAD_POSTURE": "↕",
    "USER_AWAY": "◌",
    "USER_RETURNED": "●",
    "FOCUS_RESTORED": "✓",
    "FOCUS_STREAK": "★",
}


class EventTimeline(QScrollArea):
    def __init__(self) -> None:
        super().__init__()

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFrameShape(QScrollArea.NoFrame)

        self.container = QWidget()
        self.container.setObjectName("TimelineContainer")

        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(2)
        self.layout.addStretch(1)

        self.setWidget(self.container)

    def add_event(self, event: AppEvent) -> None:
        label = QLabel(self._format(event))
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet(
            """
            QLabel {
                padding: 9px 10px;
                border-bottom: 1px solid rgba(120, 220, 255, 0.12);
                color: #c8dce5;
                background: transparent;
                font-size: 12px;
            }
            QLabel:hover {
                background: rgba(120, 220, 255, 0.06);
            }
            """
        )

        self.layout.insertWidget(0, label)

    def clear_events(self) -> None:
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _format(self, event: AppEvent) -> str:
        stamp = datetime.fromtimestamp(event.timestamp).strftime("%H:%M:%S")
        event_name = event.event_type.value
        icon = EVENT_ICONS.get(event_name, "•")
        title = event_name.replace("_", " ").title()

        if event.duration > 0:
            duration = f"  ·  {event.duration:.1f}s"
        else:
            duration = ""

        confidence = ""
        if event.confidence > 0:
            confidence = f"  ·  {event.confidence:.0%}"

        return f"{stamp}   {icon}   {title}{duration}{confidence}"