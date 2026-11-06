from __future__ import annotations

from studyguard.analytics.focus_score import FocusScore, FocusScoreCalculator
from studyguard.core.session import StudySession


class FocusEngine:
    def __init__(self) -> None:
        self.calculator = FocusScoreCalculator()

    def score(self, session: StudySession | None) -> FocusScore:
        if session is None:
            return FocusScore(score=100, explanation="Ready to start a focused session.")
        focused = max(0.0, session.elapsed - session.distraction_seconds())
        return self.calculator.calculate(session.events, focused, session.elapsed)
