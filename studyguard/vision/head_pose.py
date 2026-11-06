# studyguard/vision/head_pose.py

from __future__ import annotations

from typing import Any

from studyguard.core.config import DetectionSettings
from studyguard.vision.base import BaseDetector
from studyguard.vision.face_detector import FaceDetector
from studyguard.vision.results import DetectionResult


class AttentionDetector(BaseDetector):
    name = "attention"

    NOSE_TIP = 1
    LEFT_FACE = 234
    RIGHT_FACE = 454
    CHIN = 152
    FOREHEAD = 10

    def __init__(
        self,
        face: FaceDetector,
        settings: DetectionSettings,
    ):
        self.face = face
        self.settings = settings

        self.last_pose = "UNKNOWN"
        self.last_yaw = 0.0
        self.last_pitch = 0.0
        self.last_confidence = 0.0

    def process(
        self,
        frame: Any,
        timestamp: float,
    ) -> DetectionResult:
        marks, confidence = self.face.landmarks(frame)

        self.last_confidence = confidence

        required_landmarks = max(
            self.NOSE_TIP,
            self.LEFT_FACE,
            self.RIGHT_FACE,
            self.CHIN,
            self.FOREHEAD,
        ) + 1

        if len(marks) < required_landmarks:
            self.last_pose = "UNKNOWN"
            self.last_yaw = 0.0
            self.last_pitch = 0.0

            return DetectionResult(
                self.name,
                False,
                0.0,
                event_type=None,
                severity="info",
                metadata={
                    "pose": "UNKNOWN",
                    "yaw": 0.0,
                    "pitch": 0.0,
                    "yaw_normalized": 0.0,
                    "pitch_normalized": 0.0,
                    "face_confidence": confidence,
                    "face_visible": False,
                },
            )

        nose = marks[self.NOSE_TIP]
        left = marks[self.LEFT_FACE]
        right = marks[self.RIGHT_FACE]
        chin = marks[self.CHIN]
        forehead = marks[self.FOREHEAD]

        face_width = max(
            abs(right[0] - left[0]),
            1e-4,
        )

        face_height = max(
            abs(chin[1] - forehead[1]),
            1e-4,
        )

        center_x = (
            left[0] + right[0]
        ) / 2.0

        center_y = (
            forehead[1] + chin[1]
        ) / 2.0

        # Normalized horizontal/vertical displacement of the nose relative
        # to the face center.
        yaw_normalized = (
            nose[0] - center_x
        ) / face_width

        pitch_normalized = (
            nose[1] - center_y
        ) / face_height

        # Convert the normalized landmark displacement into a stable,
        # human-readable approximate angle.
        yaw = yaw_normalized * 70.0
        pitch = pitch_normalized * 65.0

        yaw_threshold = float(
            getattr(
                self.settings,
                "head_yaw_threshold",
                18.0,
            )
        )

        pitch_threshold = float(
            getattr(
                self.settings,
                "head_pitch_threshold",
                15.0,
            )
        )

        if yaw > yaw_threshold:
            pose = "RIGHT"
        elif yaw < -yaw_threshold:
            pose = "LEFT"
        elif pitch > pitch_threshold:
            pose = "DOWN"
        elif pitch < -pitch_threshold:
            pose = "UP"
        else:
            pose = "CENTER"

        away = pose != "CENTER"

        self.last_pose = pose
        self.last_yaw = yaw
        self.last_pitch = pitch

        return DetectionResult(
            self.name,
            away,
            confidence,
            event_type="LOOKING_AWAY" if away else None,
            severity="warning" if away else "info",
            metadata={
                "pose": pose,
                "yaw": yaw,
                "pitch": pitch,
                "yaw_normalized": yaw_normalized,
                "pitch_normalized": pitch_normalized,
                "yaw_threshold": yaw_threshold,
                "pitch_threshold": pitch_threshold,
                "looking_away": away,
                "face_confidence": confidence,
                "face_visible": True,
                "nose_point": nose[:2],
                "face_left_point": left[:2],
                "face_right_point": right[:2],
                "chin_point": chin[:2],
                "forehead_point": forehead[:2],
            },
        )