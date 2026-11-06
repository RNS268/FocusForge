# studyguard/core/events.py

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time
from typing import Any, Callable


class EventType(str, Enum):
    SESSION_START = "SESSION_START"
    SESSION_END = "SESSION_END"

    PHONE_DETECTED = "PHONE_DETECTED"
    LOOKING_AWAY = "LOOKING_AWAY"
    DROWSINESS = "DROWSINESS"
    EXCESSIVE_BLINKING = "EXCESSIVE_BLINKING"
    YAWN = "YAWN"
    BAD_POSTURE = "BAD_POSTURE"
    USER_AWAY = "USER_AWAY"
    USER_RETURNED = "USER_RETURNED"

    FOCUS_STREAK = "FOCUS_STREAK"
    FOCUS_RESTORED = "FOCUS_RESTORED"

    BREAK_START = "BREAK_START"
    BREAK_END = "BREAK_END"


@dataclass
class AppEvent:
    event_type: EventType
    timestamp: float = field(default_factory=time)
    duration: float = 0.0
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.event_type.value

    @property
    def is_distraction(self) -> bool:
        return self.event_type in {
            EventType.PHONE_DETECTED,
            EventType.LOOKING_AWAY,
            EventType.DROWSINESS,
            EventType.YAWN,
            EventType.BAD_POSTURE,
            EventType.USER_AWAY,
            EventType.EXCESSIVE_BLINKING,
        }

    @property
    def is_fatigue_event(self) -> bool:
        return self.event_type in {
            EventType.DROWSINESS,
            EventType.YAWN,
            EventType.EXCESSIVE_BLINKING,
        }

    @property
    def display_title(self) -> str:
        titles = {
            EventType.SESSION_START: "Study Session Started",
            EventType.SESSION_END: "Study Session Ended",
            EventType.PHONE_DETECTED: "Phone Detected",
            EventType.LOOKING_AWAY: "Attention Lost",
            EventType.DROWSINESS: "Drowsiness Detected",
            EventType.EXCESSIVE_BLINKING: "Excessive Blinking",
            EventType.YAWN: "Yawn Detected",
            EventType.BAD_POSTURE: "Poor Posture",
            EventType.USER_AWAY: "User Away",
            EventType.USER_RETURNED: "User Returned",
            EventType.FOCUS_STREAK: "Focus Streak",
            EventType.FOCUS_RESTORED: "Focus Restored",
            EventType.BREAK_START: "Break Started",
            EventType.BREAK_END: "Break Ended",
        }
        return titles.get(
            self.event_type,
            self.event_type.value.replace("_", " ").title(),
        )

    @property
    def display_message(self) -> str:
        messages = {
            EventType.SESSION_START: "Study monitoring is active.",
            EventType.SESSION_END: "Study session completed.",
            EventType.PHONE_DETECTED: "Put the phone away and return to studying.",
            EventType.LOOKING_AWAY: "Please return your attention to the screen.",
            EventType.DROWSINESS: "Eyes have been closed for too long.",
            EventType.EXCESSIVE_BLINKING: "Possible eye strain detected.",
            EventType.YAWN: "Fatigue detected. Consider taking a short break.",
            EventType.BAD_POSTURE: "Straighten your back and adjust your posture.",
            EventType.USER_AWAY: "You are no longer visible to the camera.",
            EventType.USER_RETURNED: "Welcome back. Monitoring resumed.",
            EventType.FOCUS_STREAK: "Excellent uninterrupted focus.",
            EventType.FOCUS_RESTORED: "Focus restored. Stay locked in.",
            EventType.BREAK_START: "Time for a break.",
            EventType.BREAK_END: "Break complete. Ready to study.",
        }
        return messages.get(self.event_type, "")

    @property
    def severity(self) -> str:
        severity_map = {
            EventType.PHONE_DETECTED: "danger",
            EventType.DROWSINESS: "danger",
            EventType.USER_AWAY: "warning",
            EventType.LOOKING_AWAY: "warning",
            EventType.BAD_POSTURE: "warning",
            EventType.EXCESSIVE_BLINKING: "warning",
            EventType.YAWN: "fatigue",
            EventType.SESSION_START: "info",
            EventType.SESSION_END: "info",
            EventType.USER_RETURNED: "success",
            EventType.FOCUS_STREAK: "success",
            EventType.FOCUS_RESTORED: "success",
            EventType.BREAK_START: "info",
            EventType.BREAK_END: "success",
        }
        return severity_map.get(self.event_type, "info")


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Callable[[AppEvent], None]] = []

    def subscribe(self, callback: Callable[[AppEvent], None]) -> None:
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[AppEvent], None]) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def publish(self, event: AppEvent) -> None:
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception:
                # One subscriber must never prevent other subscribers
                # from receiving the event.
                continue

    def clear(self) -> None:
        self._subscribers.clear()