from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionRecord:
    id: int
    started_at: float
    ended_at: float | None
    duration: float
    focused_seconds: float
    focus_score: int
    best_streak: float


@dataclass
class EventRecord:
    id: int
    session_id: int
    timestamp: float
    event_type: str
    duration: float
    confidence: float
    metadata: str
