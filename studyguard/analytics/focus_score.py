# studyguard/analytics/focus_score.py
from __future__ import annotations

from dataclasses import dataclass

from studyguard.core.events import AppEvent, EventType


PENALTIES = {
    EventType.PHONE_DETECTED: 8.0,
    EventType.LOOKING_AWAY: 4.5,
    EventType.DROWSINESS: 10.0,
    EventType.YAWN: 3.0,
    EventType.BAD_POSTURE: 2.5,
    EventType.USER_AWAY: 5.0,
    EventType.EXCESSIVE_BLINKING: 3.0,
}


@dataclass
class FocusScore:
    score: int
    explanation: str


class FocusScoreCalculator:
    def calculate(
        self,
        events: list[AppEvent],
        focused_seconds: float,
        total_seconds: float,
    ) -> FocusScore:
        score = 100.0
        counts: dict[EventType, int] = {}

        for event in events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1

            score -= PENALTIES.get(event.event_type, 0.0)

            # Duration-based penalty, capped per event so one long event
            # cannot completely dominate the score.
            score -= min(max(event.duration, 0.0) / 60.0, 5.0)

        if total_seconds > 0:
            focus_ratio = max(
                0.0,
                min(1.0, focused_seconds / total_seconds),
            )

            # Reward sustained focus, but keep the score bounded.
            if focus_ratio > 0.75:
                score += (focus_ratio - 0.75) * 16.0

        score = max(0, min(100, round(score)))

        explanation = self._explain(
            score=score,
            counts=counts,
            focused_seconds=focused_seconds,
            total_seconds=total_seconds,
        )

        return FocusScore(
            score=score,
            explanation=explanation,
        )

    def _explain(
        self,
        score: int,
        counts: dict[EventType, int],
        focused_seconds: float,
        total_seconds: float,
    ) -> str:
        distractions = sum(counts.values())

        if total_seconds > 0:
            focus_ratio = max(
                0.0,
                min(1.0, focused_seconds / total_seconds),
            )
        else:
            focus_ratio = 1.0

        if score >= 92 and focus_ratio >= 0.85:
            return "Excellent focus. You stayed consistently engaged with very few distractions."

        if score >= 88:
            if distractions == 0:
                return "Excellent focus with no detected distractions."
            return f"Strong focus with {distractions} short distractions."

        if score >= 80:
            if counts.get(EventType.PHONE_DETECTED, 0):
                return "Good focus overall, with some phone-related distractions."
            return f"Good focus with {distractions} observed distractions."

        if score >= 70:
            return f"Steady session with {distractions} observed distractions."

        if counts.get(EventType.PHONE_DETECTED, 0) >= 3:
            return "Phone distractions had the largest impact on this session."

        if counts.get(EventType.DROWSINESS, 0) or counts.get(EventType.YAWN, 0):
            return "Fatigue indicators increased; a short break may help."

        if counts.get(EventType.LOOKING_AWAY, 0) >= 3:
            return "Frequent attention shifts were detected; try keeping your gaze on your study material."

        if counts.get(EventType.BAD_POSTURE, 0) >= 3:
            return "Repeated posture issues were detected; adjust your sitting position."

        if counts.get(EventType.USER_AWAY, 0) >= 2:
            return "You spent noticeable time away from the study session."

        return "Focus was fragmented; shorter timed blocks may work better."