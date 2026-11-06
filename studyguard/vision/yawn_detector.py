# studyguard/vision/yawn_detector.py

from __future__ import annotations

from typing import Any

from studyguard.core.config import DetectionSettings
from studyguard.vision.base import BaseDetector
from studyguard.vision.face_detector import FaceDetector
from studyguard.vision.results import DetectionResult
from studyguard.vision.utils import distance


class YawnDetector(BaseDetector):
    name = "yawn"

    UPPER_LIP = 13
    LOWER_LIP = 14
    LEFT_MOUTH = 78
    RIGHT_MOUTH = 308

    def __init__(
        self,
        face: FaceDetector,
        settings: DetectionSettings,
    ):
        self.face = face
        self.settings = settings

        self.last_mar = 0.0
        self.last_confidence = 0.0

        self.yawning = False
        self.yawn_started: float | None = None
        self.last_yawn_timestamp: float | None = None

        # Prevent one long mouth opening from repeatedly producing YAWN
        # events on every frame.
        self.yawn_count = 0

    def process(
        self,
        frame: Any,
        timestamp: float,
    ) -> DetectionResult:
        marks, confidence = self.face.landmarks(frame)

        self.last_confidence = confidence

        required_landmark = max(
            self.UPPER_LIP,
            self.LOWER_LIP,
            self.LEFT_MOUTH,
            self.RIGHT_MOUTH,
        )

        if len(marks) <= required_landmark:
            self.yawning = False
            self.yawn_started = None
            self.last_mar = 0.0

            return DetectionResult(
                self.name,
                False,
                0.0,
                event_type=None,
                severity="info",
                metadata={
                    "mar": 0.0,
                    "yawning": False,
                    "yawn_duration": 0.0,
                    "face_visible": False,
                    "yawn_count": self.yawn_count,
                },
            )

        top = marks[self.UPPER_LIP]
        bottom = marks[self.LOWER_LIP]
        left = marks[self.LEFT_MOUTH]
        right = marks[self.RIGHT_MOUTH]

        mouth_width = max(
            distance(left, right),
            1e-6,
        )

        mar = distance(top, bottom) / mouth_width

        self.last_mar = mar

        threshold = float(
            getattr(
                self.settings,
                "yawn_mar_threshold",
                0.62,
            )
        )

        yawn_min_duration = max(
            0.1,
            float(
                getattr(
                    self.settings,
                    "yawn_seconds",
                    1.0,
                )
            ),
        )

        yawn_cooldown = max(
            0.0,
            float(
                getattr(
                    self.settings,
                    "yawn_cooldown",
                    3.0,
                )
            ),
        )

        mouth_open = mar >= threshold

        event_type: str | None = None

        if mouth_open:
            if self.yawn_started is None:
                self.yawn_started = timestamp

            duration = max(
                0.0,
                timestamp - self.yawn_started,
            )

            self.yawning = duration >= yawn_min_duration

        else:
            duration = (
                max(
                    0.0,
                    timestamp - self.yawn_started,
                )
                if self.yawn_started is not None
                else 0.0
            )

            completed_yawn = (
                self.yawning
                and duration >= yawn_min_duration
            )

            if completed_yawn:
                cooldown_ok = (
                    self.last_yawn_timestamp is None
                    or timestamp - self.last_yawn_timestamp
                    >= yawn_cooldown
                )

                if cooldown_ok:
                    event_type = "YAWN"
                    self.last_yawn_timestamp = timestamp
                    self.yawn_count += 1

            self.yawning = False
            self.yawn_started = None
            duration = 0.0

        current_duration = (
            max(
                0.0,
                timestamp - self.yawn_started,
            )
            if self.yawn_started is not None
            else 0.0
        )

        return DetectionResult(
            self.name,
            self.yawning or event_type == "YAWN",
            confidence,
            event_type=event_type,
            severity="fatigue" if self.yawning else "info",
            metadata={
                "mar": mar,
                "mar_threshold": threshold,
                "mouth_open": mouth_open,
                "yawning": self.yawning,
                "yawn_duration": current_duration,
                "yawn_min_duration": yawn_min_duration,
                "yawn_cooldown": yawn_cooldown,
                "yawn_count": self.yawn_count,
                "last_yawn_timestamp": self.last_yawn_timestamp,
                "face_confidence": confidence,
                "face_visible": True,
                "mouth_points": [
                    top[:2],
                    bottom[:2],
                    left[:2],
                    right[:2],
                ],
            },
        )