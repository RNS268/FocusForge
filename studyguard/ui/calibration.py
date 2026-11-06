from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from studyguard.core.config import ConfigManager
from studyguard.database.repository import Repository


class CalibrationPage(QWidget):
    steps = [
        ("LOOK STRAIGHT", 3),
        ("BLINK NORMALLY", 3),
        ("LOOK LEFT", 2),
        ("LOOK RIGHT", 2),
        ("SIT COMFORTABLY", 5),
    ]

    def __init__(self, config: ConfigManager, repo: Repository) -> None:
        super().__init__()
        self.config = config
        self.repo = repo
        self.index = 0
        self.remaining = self.steps[0][1]
        layout = QVBoxLayout(self)
        self.title = QLabel("WELCOME TO STUDYGUARD AI")
        self.title.setObjectName("Title")
        self.instruction = QLabel("")
        self.instruction.setAlignment(Qt.AlignCenter)
        self.instruction.setStyleSheet("font-size: 32px; font-weight: 800; color:#8ee8ff;")
        self.start = QPushButton("START CALIBRATION")
        self.start.clicked.connect(self.begin)
        layout.addWidget(self.title)
        layout.addStretch(1)
        layout.addWidget(self.instruction)
        layout.addStretch(1)
        layout.addWidget(self.start)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.show_step()

    def begin(self) -> None:
        self.start.setEnabled(False)
        self.timer.start(1000)

    def show_step(self) -> None:
        label, seconds = self.steps[self.index]
        self.remaining = seconds
        self.instruction.setText(f"{label}\n{seconds}s")

    def tick(self) -> None:
        self.remaining -= 1
        if self.remaining > 0:
            self.instruction.setText(f"{self.steps[self.index][0]}\n{self.remaining}s")
            return
        self.index += 1
        if self.index >= len(self.steps):
            self.timer.stop()
            self.config.config.first_run_complete = True
            self.config.config.calibration["completed_at"] = time.time()
            self.config.save()
            self.repo.save_calibration("completed_at", str(time.time()), time.time())
            self.instruction.setText("CALIBRATION COMPLETE\nYou're ready to study.")
            self.start.setText("DONE")
            self.start.setEnabled(True)
            return
        self.show_step()
