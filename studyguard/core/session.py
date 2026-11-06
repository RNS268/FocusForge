# studyguard/core/session.py

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from studyguard.core.events import AppEvent, EventType


MAJOR_DISTRACTIONS = {
    EventType.PHONE_DETECTED,
    EventType.LOOKING_AWAY,
    EventType.DROWSINESS,
    EventType.USER_AWAY,
}


@dataclass
class StudySession:
    id: int | None = None

    started_at: float = field(default_factory=monotonic)
    ended_at: float | None = None

    paused_at: float | None = None
    total_paused: float = 0.0

    focused_seconds: float = 0.0

    events: list[AppEvent] = field(default_factory=list)

    current_streak_start: float = field(
        default_factory=monotonic
    )

    best_streak: float = 0.0

    # Session analytics.
    distraction_count: int = 0
    phone_detections: int = 0
    drowsiness_events: int = 0
    looking_away_events: int = 0
    posture_events: int = 0
    yawn_events: int = 0
    excessive_blink_events: int = 0
    away_events: int = 0

    @property
    def elapsed(self) -> float:
        """
        Active session duration excluding manually paused time.
        """
        end = (
            self.ended_at
            if self.ended_at is not None
            else monotonic()
        )

        return max(
            0.0,
            end
            - self.started_at
            - self.total_paused,
        )

    @property
    def is_paused(self) -> bool:
        return self.paused_at is not None

    @property
    def is_active(self) -> bool:
        return (
            self.ended_at is None
            and not self.is_paused
        )

    @property
    def focus_ratio(self) -> float:
        """
        Percentage of active session time spent focused.
        """
        elapsed = self.elapsed

        if elapsed <= 0:
            return 0.0

        return max(
            0.0,
            min(
                1.0,
                self.focused_seconds / elapsed,
            ),
        )

    @property
    def focus_percentage(self) -> float:
        return self.focus_ratio * 100.0

    @property
    def distraction_percentage(self) -> float:
        return max(
            0.0,
            min(
                100.0,
                100.0 - self.focus_percentage,
            ),
        )

    def pause(
        self,
        now: float | None = None,
    ) -> None:
        """
        Pause the study session.

        Pausing closes the current focus streak so the paused duration is
        never accidentally counted as focused time.
        """
        if self.ended_at is not None:
            return

        if self.paused_at is not None:
            return

        current = (
            monotonic()
            if now is None
            else float(now)
        )

        self._close_streak(current)
        self.paused_at = current

    def resume(
        self,
        now: float | None = None,
    ) -> None:
        """
        Resume a previously paused study session.
        """
        if self.ended_at is not None:
            return

        if self.paused_at is None:
            return

        current = (
            monotonic()
            if now is None
            else float(now)
        )

        paused_duration = max(
            0.0,
            current - self.paused_at,
        )

        self.total_paused += paused_duration
        self.paused_at = None
        self.current_streak_start = current

    def end(
        self,
        now: float | None = None,
    ) -> None:
        """
        Finish the study session and calculate final focus statistics.
        """
        if self.ended_at is not None:
            return

        current = (
            monotonic()
            if now is None
            else float(now)
        )

        if self.paused_at is not None:
            self.resume(current)

        self._close_streak(current)

        self.ended_at = current

        active_elapsed = self.elapsed
        distraction_time = self.distraction_seconds()

        self.focused_seconds = max(
            0.0,
            active_elapsed - distraction_time,
        )

    def add_event(
        self,
        event: AppEvent,
    ) -> None:
        """
        Add an application event to the session and update analytics.
        """
        self.events.append(event)

        self._update_event_counters(event)

        if event.event_type in MAJOR_DISTRACTIONS:
            self._close_streak(event.timestamp)

            self.current_streak_start = (
                event.timestamp
                + max(0.0, event.duration)
            )

    def current_streak(
        self,
        now: float | None = None,
    ) -> float:
        """
        Return the current uninterrupted focus streak.
        """
        if self.is_paused or self.ended_at is not None:
            return 0.0

        current = (
            monotonic()
            if now is None
            else float(now)
        )

        return max(
            0.0,
            current - self.current_streak_start,
        )

    def _close_streak(
        self,
        now: float,
    ) -> None:
        """
        Close the current focus streak and update the best streak.
        """
        streak = max(
            0.0,
            now - self.current_streak_start,
        )

        self.best_streak = max(
            self.best_streak,
            streak,
        )

    def distraction_seconds(self) -> float:
        """
        Total duration attributable to major distractions.

        Overlapping events are not double-counted here because the session
        event model does not yet maintain interval merging. This method
        intentionally preserves event durations as recorded by EventEngine.
        """
        return sum(
            max(0.0, event.duration)
            for event in self.events
            if event.event_type in MAJOR_DISTRACTIONS
        )

    def _update_event_counters(
        self,
        event: AppEvent,
    ) -> None:
        """
        Maintain lightweight session analytics for the dashboard.
        """
        event_type = event.event_type

        if event_type in MAJOR_DISTRACTIONS:
            self.distraction_count += 1

        if event_type == EventType.PHONE_DETECTED:
            self.phone_detections += 1

        elif event_type == EventType.DROWSINESS:
            self.drowsiness_events += 1

        elif event_type == EventType.LOOKING_AWAY:
            self.looking_away_events += 1

        elif event_type == EventType.BAD_POSTURE:
            self.posture_events += 1

        elif event_type == EventType.YAWN:
            self.yawn_events += 1

        elif event_type == EventType.EXCESSIVE_BLINKING:
            self.excessive_blink_events += 1

        elif event_type == EventType.USER_AWAY:
            self.away_events += 1

    def summary(
        self,
        now: float | None = None,
    ) -> dict[str, Any]:
        """
        Return session metrics for the futuristic dashboard/HUD.
        """
        current = (
            monotonic()
            if now is None
            else float(now)
        )

        return {
            "id": self.id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "elapsed": self.elapsed,
            "focused_seconds": self.focused_seconds,
            "distraction_seconds": self.distraction_seconds(),
            "total_paused": self.total_paused,
            "current_streak": self.current_streak(current),
            "best_streak": self.best_streak,
            "focus_ratio": self.focus_ratio,
            "focus_percentage": self.focus_percentage,
            "distraction_percentage": self.distraction_percentage,
            "is_paused": self.is_paused,
            "is_active": self.is_active,
            "event_count": len(self.events),
            "distraction_count": self.distraction_count,
            "phone_detections": self.phone_detections,
            "drowsiness_events": self.drowsiness_events,
            "looking_away_events": self.looking_away_events,
            "posture_events": self.posture_events,
            "yawn_events": self.yawn_events,
            "excessive_blink_events": self.excessive_blink_events,
            "away_events": self.away_events,
        }

    def reset_statistics(self) -> None:
        """
        Reset session event statistics while preserving session timing.
        """
        self.events.clear()

        self.focused_seconds = 0.0
        self.best_streak = 0.0

        self.distraction_count = 0
        self.phone_detections = 0
        self.drowsiness_events = 0
        self.looking_away_events = 0
        self.posture_events = 0
        self.yawn_events = 0
        self.excessive_blink_events = 0
        self.away_events = 0

        current = monotonic()

        self.current_streak_start = current