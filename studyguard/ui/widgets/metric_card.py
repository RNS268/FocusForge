# studyguard/ui/widgets/metric_card.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class MetricCard(QFrame):
    def __init__(self, title: str, value: str = "--", subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)

        self.title = QLabel(title.upper())
        self.title.setObjectName("Mono")
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.value = QLabel(value)
        self.value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.value.setStyleSheet(
            """
            QLabel {
                font-size: 32px;
                font-weight: 750;
                color: #ffffff;
                background: transparent;
            }
            """
        )

        self.subtitle = QLabel(subtitle)
        self.subtitle.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.subtitle.setWordWrap(True)
        self.subtitle.setStyleSheet(
            """
            QLabel {
                color: #8aa8b8;
                font-size: 12px;
                background: transparent;
            }
            """
        )

        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.subtitle)

    def set_value(self, value: str, subtitle: str | None = None) -> None:
        self.value.setText(value)
        if subtitle is not None:
            self.subtitle.setText(subtitle)