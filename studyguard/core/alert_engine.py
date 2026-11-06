# studyguard/core/alert_engine.py

from __future__ import annotations

from collections import defaultdict
from time import time
from typing import Any

from studyguard.core.config import AudioSettings
from studyguard.core.events import AppEvent


class AlertEngine:
    """
    Controls when an application event is allowed to trigger an alert.

    EventEngine handles detection persistence/debouncing.
    AlertEngine handles audio/notification cooldowns so repeated detector
    events do not continuously interrupt the study session.
    """

    DEFAULT_COOLDOWNS = {
        "DROWSINESS": 15.0,
        "PHONE_DETECTED": 10.0,
        "LOOKING_AWAY": 15.0,
        "BAD_POSTURE": 20.0,
        "YAWN": 20.0,
        "EXCESSIVE_BLINKING": 20.0,
        "USER_AWAY": 10.0,
    }

    def __init__(self, settings: AudioSettings) -> None:
        self.settings = settings

        self.last_alert_at: dict[str, float] = defaultdict(
            lambda: -1e9
        )

        # Tracks alert count for session analytics/debugging.
        self.alert_counts: dict[str, int] = defaultdict(int)

        # Tracks the newest event timestamp received for each event type.
        self.last_event_timestamp: dict[str, float] = {}

    def can_alert(
        self,
        event_type: str,
        now: float | None = None,
    ) -> bool:
        """
        Return True when the supplied event is currently allowed to alert.
        """
        current = time() if now is None else float(now)

        cooldown = self._cooldown(event_type)
        last_alert = self.last_alert_at[event_type]

        return current - last_alert >= cooldown

    def mark_alerted(self, event: AppEvent) -> None:
        """
        Record that an event has actually produced an alert.

        Event timestamps use the same wall-clock time source as the rest
        of the StudyGuard runtime.
        """
        event_type = event.event_type.value
        timestamp = float(event.timestamp)

        # Protect against an older event arriving after a newer event.
        previous_timestamp = self.last_event_timestamp.get(event_type)

        if (
            previous_timestamp is not None
            and timestamp < previous_timestamp
        ):
            return

        self.last_event_timestamp[event_type] = timestamp
        self.last_alert_at[event_type] = timestamp
        self.alert_counts[event_type] += 1

    def _cooldown(self, event_type: str) -> float:
        """
        Resolve the cooldown from AudioSettings with safe defaults.
        """
        configured = None

        try:
            configured = self.settings.cooldowns.get(event_type)
        except (AttributeError, TypeError):
            configured = None

        if configured is None:
            configured = self.DEFAULT_COOLDOWNS.get(
                event_type,
                10.0,
            )

        try:
            return max(
                0.0,
                float(configured),
            )
        except (TypeError, ValueError):
            return self.DEFAULT_COOLDOWNS.get(
                event_type,
                10.0,
            )

    def remaining_cooldown(
        self,
        event_type: str,
        now: float | None = None,
    ) -> float:
        """
        Return remaining cooldown seconds for an event.

        Returns 0 when the event can alert immediately.
        """
        current = time() if now is None else float(now)

        elapsed = current - self.last_alert_at[event_type]

        return max(
            0.0,
            self._cooldown(event_type) - elapsed,
        )

    def reset(self, event_type: str | None = None) -> None:
        """
        Reset alert cooldown state.

        If event_type is omitted, reset the entire alert engine.
        """
        if event_type is None:
            self.last_alert_at.clear()
            self.alert_counts.clear()
            self.last_event_timestamp.clear()
            return

        self.last_alert_at.pop(event_type, None)
        self.alert_counts.pop(event_type, None)
        self.last_event_timestamp.pop(event_type, None)

    def get_alert_count(self, event_type: str) -> int:
        """
        Return how many alerts of a specific type have fired.
        """
        return self.alert_counts.get(event_type, 0)

    def snapshot(self) -> dict[str, Any]:
        """
        Return lightweight runtime state for the HUD/dashboard.
        """
        return {
            "last_alert_at": dict(self.last_alert_at),
            "alert_counts": dict(self.alert_counts),
            "cooldowns": {
                event_type: self._cooldown(event_type)
                for event_type in self.DEFAULT_COOLDOWNS
            },
        }