from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class AppState(str, Enum):
    IDLE = "IDLE"
    INITIALIZING = "INITIALIZING"
    CALIBRATING = "CALIBRATING"
    READY = "READY"
    STUDYING = "STUDYING"
    PAUSED = "PAUSED"
    BREAK = "BREAK"
    CAMERA_ERROR = "CAMERA_ERROR"
    SESSION_COMPLETE = "SESSION_COMPLETE"


@dataclass
class StateTransition:
    previous: AppState
    current: AppState


class StateManager:
    def __init__(self) -> None:
        self.state = AppState.INITIALIZING
        self._subscribers: list[Callable[[StateTransition], None]] = []

    def subscribe(self, callback: Callable[[StateTransition], None]) -> None:
        self._subscribers.append(callback)

    def set(self, state: AppState) -> None:
        if state == self.state:
            return
        transition = StateTransition(previous=self.state, current=state)
        self.state = state
        for callback in self._subscribers:
            callback(transition)
