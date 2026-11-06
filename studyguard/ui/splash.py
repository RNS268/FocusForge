from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SplashScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.SplashScreen)
        self.resize(560, 360)
        self.setStyleSheet(
            """
            QWidget { background: #060910; border: 1px solid #45d9ff; border-radius: 8px; }
            QLabel { color: #e7f6ff; background: transparent; }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 30, 34, 30)
        title = QLabel("STUDYGUARD AI")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 34px; font-weight: 850;")
        subtitle = QLabel("Initializing your focus environment...")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color:#8ee8ff; font-family:'Cascadia Mono', Consolas;")
        statuses = QLabel(
            "OK  Camera\n"
            "OK  Face tracking\n"
            "OK  Hand tracking\n"
            "OK  Attention engine\n"
            "OK  Phone detection\n"
            "OK  Audio engine\n"
            "OK  Study database"
        )
        statuses.setStyleSheet("font-family:'Cascadia Mono', Consolas; font-size: 15px; line-height: 1.4;")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch(1)
        layout.addWidget(statuses)
