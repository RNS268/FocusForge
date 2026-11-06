from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from studyguard.database.repository import Repository


class TinyChart(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.values: list[float] = []
        self.setMinimumHeight(130)

    def set_values(self, values: list[float]) -> None:
        self.values = values
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.transparent)
        if len(self.values) < 2:
            painter.setPen(QPen(Qt.cyan))
            painter.drawText(16, 64, "No chart data yet")
            return
        max_v = max(max(self.values), 1.0)
        step = self.width() / (len(self.values) - 1)
        points = []
        for i, value in enumerate(self.values):
            x = i * step
            y = self.height() - (value / max_v) * (self.height() - 20) - 10
            points.append((x, y))
        painter.setPen(QPen(Qt.cyan, 2))
        for a, b in zip(points, points[1:]):
            painter.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))


class AnalyticsPage(QWidget):
    def __init__(self, repo: Repository) -> None:
        super().__init__()
        self.repo = repo
        layout = QVBoxLayout(self)
        title = QLabel("ANALYTICS")
        title.setObjectName("Title")
        layout.addWidget(title)
        self.chart = TinyChart()
        layout.addWidget(self.chart)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Started", "Duration", "Focused", "Score", "Best Streak"])
        layout.addWidget(self.table)

    def refresh(self) -> None:
        sessions = self.repo.sessions(50)
        self.table.setRowCount(len(sessions))
        self.chart.set_values([float(s["focus_score"]) for s in reversed(sessions)])
        for row, session in enumerate(sessions):
            values = [
                datetime.fromtimestamp(session["started_at"]).strftime("%Y-%m-%d %H:%M"),
                self._fmt(session["duration"]),
                self._fmt(session["focused_seconds"]),
                f'{session["focus_score"]}%',
                self._fmt(session["best_streak"]),
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(value))

    def _fmt(self, seconds: float) -> str:
        seconds = int(seconds or 0)
        return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
