# studyguard/ui/dashboard.py

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from studyguard.ui.camera_view import CameraView
from studyguard.ui.widgets.metric_card import MetricCard
from studyguard.ui.widgets.timeline import EventTimeline


class Dashboard(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("Dashboard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        # ─────────────────────────────────────────────
        # HEADER
        # ─────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(14)

        title_container = QVBoxLayout()
        title_container.setSpacing(0)

        self.title = QLabel("STUDYGUARD")
        self.title.setObjectName("Title")

        self.subtitle = QLabel("AI STUDY MONITOR  //  FOCUS INTELLIGENCE")
        self.subtitle.setObjectName("Mono")

        title_container.addWidget(self.title)
        title_container.addWidget(self.subtitle)

        top.addLayout(title_container)
        top.addStretch(1)

        self.status = QLabel("● SYSTEM INITIALIZING")
        self.status.setObjectName("Mono")
        self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        top.addWidget(self.status)

        layout.addLayout(top)

        # ─────────────────────────────────────────────
        # CAMERA / VISION AREA
        # ─────────────────────────────────────────────
        camera_frame = QFrame()
        camera_frame.setObjectName("CameraContainer")

        camera_layout = QVBoxLayout(camera_frame)
        camera_layout.setContentsMargins(2, 2, 2, 2)

        self.camera = CameraView()
        camera_layout.addWidget(self.camera)

        layout.addWidget(camera_frame, 6)

        # ─────────────────────────────────────────────
        # METRICS
        # ─────────────────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(10)

        self.focus = MetricCard(
            "FOCUS SCORE",
            "100%",
            "READY",
        )

        self.session = MetricCard(
            "STUDY SESSION",
            "00:00:00",
            "FOCUSED: 00:00:00",
        )

        self.streak = MetricCard(
            "CURRENT STREAK",
            "00:00",
            "BEST: 00:00",
        )

        self.today = MetricCard(
            "TODAY",
            "0m",
            "NO DISTRACTIONS",
        )

        grid.addWidget(self.focus, 0, 0)
        grid.addWidget(self.session, 0, 1)
        grid.addWidget(self.streak, 0, 2)
        grid.addWidget(self.today, 0, 3)

        layout.addLayout(grid)

        # ─────────────────────────────────────────────
        # LIVE STATUS + TIMELINE
        # ─────────────────────────────────────────────
        lower = QHBoxLayout()
        lower.setSpacing(10)

        live = QFrame()
        live.setObjectName("Card")

        live_layout = QVBoxLayout(live)
        live_layout.setContentsMargins(16, 14, 16, 14)
        live_layout.setSpacing(8)

        live_header = QHBoxLayout()

        live_title = QLabel("LIVE STATUS")
        live_title.setObjectName("SectionTitle")

        self.live_indicator = QLabel("● MONITORING")
        self.live_indicator.setObjectName("Mono")
        self.live_indicator.setAlignment(Qt.AlignRight)

        live_header.addWidget(live_title)
        live_header.addStretch(1)
        live_header.addWidget(self.live_indicator)

        live_layout.addLayout(live_header)

        self.live_status = QLabel(
            "ATTENTION     HIGH\n"
            "EYES          OPEN\n"
            "PHONE         CLEAR\n"
            "HANDS         CLEAR\n"
            "POSTURE       GOOD\n"
            "FATIGUE       LOW\n"
            "CAMERA        ACTIVE\n"
            "\n"
            "LOCAL PROCESSING ACTIVE"
        )
        self.live_status.setObjectName("Mono")
        self.live_status.setTextFormat(Qt.PlainText)
        live_layout.addWidget(self.live_status)
        live_layout.addStretch(1)

        self.timeline = EventTimeline()

        lower.addWidget(live, 1)
        lower.addWidget(self.timeline, 2)

        layout.addLayout(lower, 2)

        # ─────────────────────────────────────────────
        # CONTROLS
        # ─────────────────────────────────────────────
        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.start_button = QPushButton("▶  START STUDY SESSION")
        self.start_button.setObjectName("Primary")

        self.stop_button = QPushButton("■  STOP")
        self.stop_button.setObjectName("Danger")

        self.analytics_button = QPushButton("◫  ANALYTICS")
        self.settings_button = QPushButton("⚙  SETTINGS")
        self.calibrate_button = QPushButton("◎  RECALIBRATE")

        for button in [
            self.start_button,
            self.stop_button,
            self.analytics_button,
            self.settings_button,
            self.calibrate_button,
        ]:
            button.setMinimumHeight(38)
            controls.addWidget(button)

        layout.addLayout(controls)

    def set_online(self, online: bool, focus: int) -> None:
        focus = max(0, min(100, int(focus)))

        if online:
            self.status.setText(
                f"● SYSTEM ONLINE   //   FOCUS {focus}%   //   LOCAL PROCESSING"
            )
            self.live_indicator.setText("● MONITORING")
        else:
            self.status.setText(
                f"● CAMERA DEGRADED   //   FOCUS {focus}%   //   TIMER MODE"
            )
            self.live_indicator.setText("● DEGRADED")

    def set_live_status(
        self,
        attention: str = "HIGH",
        eyes: str = "OPEN",
        phone: str = "CLEAR",
        hands: str = "CLEAR",
        posture: str = "GOOD",
        fatigue: str = "LOW",
        camera: str = "ACTIVE",
    ) -> None:
        self.live_status.setText(
            f"ATTENTION     {attention.upper()}\n"
            f"EYES          {eyes.upper()}\n"
            f"PHONE         {phone.upper()}\n"
            f"HANDS         {hands.upper()}\n"
            f"POSTURE       {posture.upper()}\n"
            f"FATIGUE       {fatigue.upper()}\n"
            f"CAMERA        {camera.upper()}\n"
            "\n"
            "LOCAL PROCESSING ACTIVE"
        )

    def set_session_metrics(
        self,
        focus: int | None = None,
        elapsed: str | None = None,
        focused: str | None = None,
        streak: str | None = None,
        best_streak: str | None = None,
        today: str | None = None,
        distraction_text: str | None = None,
    ) -> None:
        if focus is not None:
            focus = max(0, min(100, int(focus)))
            self.focus.set_values(
                f"{focus}%",
                "FOCUSING" if focus >= 70 else "DISTRACTED",
            )

        if elapsed is not None:
            self.session.set_values(
                elapsed,
                f"FOCUSED: {focused or '00:00:00'}",
            )

        if streak is not None:
            self.streak.set_values(
                streak,
                f"BEST: {best_streak or '00:00'}",
            )

        if today is not None:
            self.today.set_values(
                today,
                distraction_text or "NO DISTRACTIONS",
            )

    def paintEvent(self, event) -> None:
        super().paintEvent(event)

        # Very subtle futuristic HUD corner accents around the dashboard.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        pen = QPen(QColor("#8ee8ff"))
        pen.setWidth(1)
        painter.setPen(pen)

        margin = 6
        length = 18

        # Top-left
        painter.drawLine(margin, margin, margin + length, margin)
        painter.drawLine(margin, margin, margin, margin + length)

        # Top-right
        painter.drawLine(
            self.width() - margin - length,
            margin,
            self.width() - margin,
            margin,
        )
        painter.drawLine(
            self.width() - margin,
            margin,
            self.width() - margin,
            margin + length,
        )

        # Bottom-left
        painter.drawLine(
            margin,
            self.height() - margin,
            margin + length,
            self.height() - margin,
        )
        painter.drawLine(
            margin,
            self.height() - margin - length,
            margin,
            self.height() - margin,
        )

        # Bottom-right
        painter.drawLine(
            self.width() - margin - length,
            self.height() - margin,
            self.width() - margin,
            self.height() - margin,
        )
        painter.drawLine(
            self.width() - margin,
            self.height() - margin - length,
            self.width() - margin,
            self.height() - margin,
        )

        painter.end()