from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from studyguard.analytics.focus_score import FocusScore
from studyguard.core.session import StudySession
from studyguard.ui.widgets.metric_card import MetricCard


def fmt(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


class SessionSummary(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("SESSION COMPLETE")
        title.setObjectName("Title")
        layout.addWidget(title)
        self.duration = MetricCard("Duration")
        self.score = MetricCard("Focus Score")
        self.focused = MetricCard("Focused Time")
        self.distractions = MetricCard("Distractions")
        self.best = MetricCard("Best Streak")
        self.note = QLabel("")
        for widget in [self.duration, self.score, self.focused, self.distractions, self.best, self.note]:
            layout.addWidget(widget)

    def load(self, session: StudySession, score: FocusScore) -> None:
        self.duration.set_value(fmt(session.elapsed))
        self.score.set_value(f"{score.score}%")
        self.focused.set_value(fmt(session.focused_seconds))
        self.distractions.set_value(str(len(session.events)))
        self.best.set_value(fmt(session.best_streak))
        self.note.setText(score.explanation)
