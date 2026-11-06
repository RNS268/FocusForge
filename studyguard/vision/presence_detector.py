# studyguard/vision/presence_detector.py

from __future__ import annotations

from typing import Any

from studyguard.vision.base import BaseDetector
from studyguard.vision.face_detector import FaceDetector
from studyguard.vision.results import DetectionResult


class PresenceDetector(BaseDetector):
    name = "presence"

    def __init__(self, face: FaceDetector):
        self.face = face

        self.state = "UNKNOWN"
        self.last_confidence = 0.0
        self.last_seen_timestamp: float | None = None
        self.missing_since: float | None = None

    def process(
        self,
        frame: Any,
        timestamp: float,
    ) -> DetectionResult:
        marks, confidence = self.face.landmarks(frame)

        present = bool(marks)

        if present:
            self.state = "PRESENT"
            self.last_seen_timestamp = timestamp
            self.missing_since = None
            self.last_confidence = confidence

            return DetectionResult(
                self.name,
                False,
                confidence,
                event_type=None,
                severity="info",
                metadata={
                    "presence": self.state,
                    "present": True,
                    "face_visible": True,
                    "face_confidence": confidence,
                    "missing_duration": 0.0,
                    "last_seen_timestamp": self.last_seen_timestamp,
                },
            )

        if self.missing_since is None:
            self.missing_since = timestamp

        missing_duration = max(
            0.0,
            timestamp - self.missing_since,
        )

        # Distinguish a temporarily lost face from a user who has actually
        # left the study area. The event engine can still apply its own
        # persistence/cooldown rules.
        state = (
            "FACE_MISSING"
            if self.last_seen_timestamp is not None
            else "FACE_NOT_DETECTED"
        )

        self.state = state
        self.last_confidence = 0.0

        return DetectionResult(
            self.name,
            True,
            0.0,
            event_type="USER_AWAY",
            severity="warning",
            metadata={
                "presence": state,
                "present": False,
                "face_visible": False,
                "face_confidence": 0.0,
                "missing_duration": missing_duration,
                "missing_since": self.missing_since,
                "last_seen_timestamp": self.last_seen_timestamp,
            },
        )