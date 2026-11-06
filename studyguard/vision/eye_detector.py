from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Any

from studyguard.core.config import DetectionSettings
from studyguard.vision.base import BaseDetector
from studyguard.vision.face_detector import FaceDetector
from studyguard.vision.results import DetectionResult
from studyguard.vision.utils import distance


class EyeState(str, Enum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    DROWSY = "DROWSY"


LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]


class EyeDetector(BaseDetector):
    name = "eyes"

    def __init__(self, face: FaceDetector, settings: DetectionSettings):
        self.face = face
        self.settings = settings

        self.state = EyeState.OPEN

        # Timestamp at which a continuous eye-closure started.
        self.closed_since: float | None = None

        # Blink timestamps are retained for one minute.
        self.blinks: deque[float] = deque(maxlen=120)

        # Small EAR history reduces single-frame noise.
        self.ear_history: deque[float] = deque(maxlen=5)

        # Last measurements exposed to the HUD/debug UI.
        self.last_ear = 0.32
        self.last_left_ear = 0.32
        self.last_right_ear = 0.32

        # Last known face confidence.
        self.last_confidence = 0.0

        # Used to prevent the same continuous closure from being counted
        # as multiple blinks.
        self._blink_in_progress = False

    def process(self, frame: Any, timestamp: float) -> DetectionResult:
        marks, confidence = self.face.landmarks(frame)
        self.last_confidence = confidence

        if not marks:
            self._reset_for_missing_face()

            return DetectionResult(
                self.name,
                False,
                0.0,
                metadata={
                    "state": self.state.value,
                    "ear": self.last_ear,
                    "left_ear": self.last_left_ear,
                    "right_ear": self.last_right_ear,
                    "closed": False,
                    "blinks_per_minute": self._recent_blink_count(timestamp),
                    "eye_points": [],
                    "face_missing": True,
                },
            )

        left_ear = self._ear(marks, LEFT_EYE)
        right_ear = self._ear(marks, RIGHT_EYE)

        self.last_left_ear = left_ear
        self.last_right_ear = right_ear

        raw_ear = (left_ear + right_ear) / 2.0

        self.ear_history.append(raw_ear)

        # Median smoothing is deliberately used instead of a simple moving
        # average so a single bad landmark frame does not keep the eyes
        # falsely classified as closed.
        ear = self._smoothed_ear()

        self.last_ear = ear

        threshold = float(
            getattr(
                self.settings,
                "eye_ear_threshold",
                0.21,
            )
        )

        closed = ear < threshold

        drowsy_seconds = max(
            0.1,
            float(
                getattr(
                    self.settings,
                    "drowsy_seconds",
                    1.5,
                )
            ),
        )

        blink_window_seconds = max(
            0.05,
            float(
                getattr(
                    self.settings,
                    "blink_window_seconds",
                    0.8,
                )
            ),
        )

        if closed:
            self._handle_closed_eyes(timestamp, drowsy_seconds)
        else:
            self._handle_open_eyes(timestamp, blink_window_seconds)

        recent_blinks = self._recent_blink_count(timestamp)

        excessive_blinks_limit = max(
            1,
            int(
                getattr(
                    self.settings,
                    "excessive_blinks_per_minute",
                    30,
                )
            ),
        )

        event_type: str | None = None
        severity = "warning"

        # Drowsiness takes priority over excessive blinking.
        if self.state == EyeState.DROWSY:
            event_type = "DROWSINESS"
            severity = "danger"
        elif recent_blinks >= excessive_blinks_limit:
            event_type = "EXCESSIVE_BLINKING"
            severity = "warning"

        eye_points = [
            marks[i][:2]
            for i in LEFT_EYE + RIGHT_EYE
            if i < len(marks)
        ]

        closed_duration = 0.0
        if self.closed_since is not None:
            closed_duration = max(0.0, timestamp - self.closed_since)

        return DetectionResult(
            self.name,
            event_type is not None,
            confidence,
            event_type=event_type,
            severity=severity,
            metadata={
                # Primary combined metric.
                "ear": ear,

                # Individual eye metrics are useful for the developer HUD
                # and future asymmetric-eye handling.
                "left_ear": left_ear,
                "right_ear": right_ear,

                # Current eye state.
                "state": self.state.value,
                "closed": closed,

                # How long the current closure has lasted.
                "closed_duration": closed_duration,

                # Blink statistics.
                "blinks_per_minute": recent_blinks,

                # Detection threshold used for this frame.
                "ear_threshold": threshold,

                # Face confidence.
                "face_confidence": confidence,

                # Landmark coordinates for drawing futuristic eye outlines.
                "eye_points": eye_points,

                "face_missing": False,
            },
        )

    def _handle_closed_eyes(
        self,
        timestamp: float,
        drowsy_seconds: float,
    ) -> None:
        """
        Handle a continuous period of eye closure.

        A normal blink becomes CLOSING/CLOSED.

        If the closure exceeds drowsy_seconds it becomes DROWSY.
        """
        if self.closed_since is None:
            self.closed_since = timestamp
            self._blink_in_progress = True
            self.state = EyeState.CLOSING
            return

        elapsed = max(0.0, timestamp - self.closed_since)

        if elapsed >= drowsy_seconds:
            self.state = EyeState.DROWSY
        else:
            self.state = EyeState.CLOSED

    def _handle_open_eyes(
        self,
        timestamp: float,
        blink_window_seconds: float,
    ) -> None:
        """
        Handle eyes reopening.

        A short closure is counted as one blink. A long closure is treated
        as drowsiness and is not counted as a normal blink.
        """
        if self.closed_since is not None:
            elapsed = max(0.0, timestamp - self.closed_since)

            if (
                self._blink_in_progress
                and elapsed <= blink_window_seconds
            ):
                self.blinks.append(timestamp)

        self.closed_since = None
        self._blink_in_progress = False
        self.state = EyeState.OPEN

    def _reset_for_missing_face(self) -> None:
        """
        Reset transient eye state when the face is unavailable.

        Do not carry a previous closed-eye state across a period where the
        face is no longer visible.
        """
        self.closed_since = None
        self._blink_in_progress = False
        self.state = EyeState.OPEN

        # Keep the last EAR values for HUD continuity rather than replacing
        # them with zero.
        self.ear_history.clear()

    def _recent_blink_count(self, timestamp: float) -> int:
        """
        Remove blink timestamps older than one minute and return the count.
        """
        cutoff = timestamp - 60.0

        while self.blinks and self.blinks[0] < cutoff:
            self.blinks.popleft()

        return len(self.blinks)

    def _smoothed_ear(self) -> float:
        """
        Return a robust EAR estimate.

        Median smoothing handles occasional landmark jumps better than a
        simple average.
        """
        if not self.ear_history:
            return self.last_ear

        values = sorted(self.ear_history)
        middle = len(values) // 2

        if len(values) % 2:
            return values[middle]

        return (values[middle - 1] + values[middle]) / 2.0

    def _ear(
        self,
        marks: list[tuple[float, float, float]],
        indexes: list[int],
    ) -> float:
        """
        Calculate Eye Aspect Ratio from six MediaPipe eye landmarks.

        Landmark order:

            p0 -------- p3
             \          /
              p1      p2
              |        |
              p5      p4
        """
        if any(index >= len(marks) for index in indexes):
            return 0.0

        p = [marks[index] for index in indexes]

        vertical = (
            distance(p[1], p[5])
            + distance(p[2], p[4])
        )

        horizontal = 2.0 * distance(p[0], p[3])

        if horizontal <= 1e-8:
            return 0.0

        return vertical / horizontal