# studyguard/vision/posture_detector.py

from __future__ import annotations

from math import atan2, degrees
from typing import Any

from studyguard.vision.base import BaseDetector
from studyguard.vision.results import DetectionResult


class PostureDetector(BaseDetector):
    name = "posture"

    NOSE = 0
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_EAR = 7
    RIGHT_EAR = 8
    LEFT_HIP = 23
    RIGHT_HIP = 24

    def __init__(self) -> None:
        self.available = False
        self._pose = None

        self.last_state = "UNKNOWN"
        self.last_score = 1.0
        self.last_confidence = 0.0

        self.last_tilt = 0.0
        self.last_head_forward = 0.0
        self.last_lean = 0.0

        try:
            import mediapipe as mp

            self._pose = mp.solutions.pose.Pose(
                static_image_mode=False,
                model_complexity=1,
                smooth_landmarks=True,
                enable_segmentation=False,
                min_detection_confidence=0.55,
                min_tracking_confidence=0.55,
            )

            self.available = True

        except Exception:
            self._pose = None
            self.available = False

    def process(
        self,
        frame: Any,
        timestamp: float,
    ) -> DetectionResult:
        if not self.available or self._pose is None:
            self._reset_state()

            return DetectionResult(
                self.name,
                False,
                0.0,
                event_type=None,
                severity="info",
                metadata={
                    "available": False,
                    "posture": "UNKNOWN",
                    "score": 0.0,
                    "confidence": 0.0,
                    "tilt": 0.0,
                    "shoulder_tilt_degrees": 0.0,
                    "head_forward": 0.0,
                    "lean": 0.0,
                    "landmarks": [],
                },
            )

        try:
            import cv2

            rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB,
            )

            results = self._pose.process(rgb)

        except Exception:
            self._reset_state()

            return DetectionResult(
                self.name,
                False,
                0.0,
                event_type=None,
                severity="info",
                metadata={
                    "available": True,
                    "posture": "UNKNOWN",
                    "score": 0.0,
                    "confidence": 0.0,
                    "tilt": 0.0,
                    "shoulder_tilt_degrees": 0.0,
                    "head_forward": 0.0,
                    "lean": 0.0,
                    "landmarks": [],
                    "processing_error": True,
                },
            )

        if not results.pose_landmarks:
            self._reset_state()

            return DetectionResult(
                self.name,
                False,
                0.0,
                event_type=None,
                severity="info",
                metadata={
                    "available": True,
                    "posture": "UNKNOWN",
                    "score": 0.0,
                    "confidence": 0.0,
                    "tilt": 0.0,
                    "shoulder_tilt_degrees": 0.0,
                    "head_forward": 0.0,
                    "lean": 0.0,
                    "landmarks": [],
                },
            )

        landmarks = results.pose_landmarks.landmark

        required_indices = (
            self.NOSE,
            self.LEFT_SHOULDER,
            self.RIGHT_SHOULDER,
        )

        if any(
            index >= len(landmarks)
            for index in required_indices
        ):
            self._reset_state()

            return DetectionResult(
                self.name,
                False,
                0.0,
                event_type=None,
                severity="info",
                metadata={
                    "available": True,
                    "posture": "UNKNOWN",
                    "score": 0.0,
                    "confidence": 0.0,
                    "tilt": 0.0,
                    "shoulder_tilt_degrees": 0.0,
                    "head_forward": 0.0,
                    "lean": 0.0,
                    "landmarks": [],
                },
            )

        nose = landmarks[self.NOSE]
        left_shoulder = landmarks[self.LEFT_SHOULDER]
        right_shoulder = landmarks[self.RIGHT_SHOULDER]

        shoulder_mid_x = (
            left_shoulder.x + right_shoulder.x
        ) / 2.0

        shoulder_mid_y = (
            left_shoulder.y + right_shoulder.y
        ) / 2.0

        shoulder_width = max(
            abs(
                right_shoulder.x
                - left_shoulder.x
            ),
            1e-6,
        )

        shoulder_height = max(
            abs(
                right_shoulder.y
                - left_shoulder.y
            ),
            0.0,
        )

        # Normalize shoulder tilt against shoulder width so the score is
        # less dependent on how far the user is from the camera.
        shoulder_tilt = (
            shoulder_height / shoulder_width
        )

        shoulder_tilt_degrees = abs(
            degrees(
                atan2(
                    right_shoulder.y
                    - left_shoulder.y,
                    right_shoulder.x
                    - left_shoulder.x,
                )
            )
        )

        # A larger value means the head is positioned further down relative
        # to the shoulder line. This is a useful proxy for slouching.
        head_forward = max(
            0.0,
            nose.y - shoulder_mid_y,
        )

        # Normalize lateral head displacement against shoulder width.
        lean = abs(
            nose.x - shoulder_mid_x
        ) / shoulder_width

        # Clamp each penalty so one noisy landmark does not make the score
        # completely collapse.
        tilt_penalty = min(
            0.45,
            shoulder_tilt * 3.0,
        )

        head_penalty = min(
            0.40,
            head_forward * 2.2,
        )

        lean_penalty = min(
            0.30,
            lean * 0.65,
        )

        posture_score = max(
            0.0,
            min(
                1.0,
                1.0
                - tilt_penalty
                - head_penalty
                - lean_penalty,
            ),
        )

        if posture_score < 0.55:
            state = "POOR"
        elif posture_score < 0.75:
            state = "FAIR"
        else:
            state = "GOOD"

        poor = state == "POOR"

        # MediaPipe's visibility values provide a more useful confidence
        # estimate than assuming every detected pose is equally reliable.
        visibility_values = [
            float(getattr(nose, "visibility", 1.0)),
            float(
                getattr(
                    left_shoulder,
                    "visibility",
                    1.0,
                )
            ),
            float(
                getattr(
                    right_shoulder,
                    "visibility",
                    1.0,
                )
            ),
        ]

        confidence = sum(
            visibility_values
        ) / len(visibility_values)

        confidence = max(
            0.0,
            min(1.0, confidence),
        )

        self.last_state = state
        self.last_score = posture_score
        self.last_confidence = confidence
        self.last_tilt = shoulder_tilt
        self.last_head_forward = head_forward
        self.last_lean = lean

        landmark_points = [
            (
                float(landmark.x),
                float(landmark.y),
            )
            for landmark in landmarks
        ]

        return DetectionResult(
            self.name,
            poor,
            confidence,
            event_type="BAD_POSTURE" if poor else None,
            severity="warning" if poor else "info",
            metadata={
                "available": True,
                "posture": state,
                "score": posture_score,
                "confidence": confidence,
                "tilt": shoulder_tilt,
                "shoulder_tilt_degrees": shoulder_tilt_degrees,
                "head_forward": head_forward,
                "lean": lean,
                "poor_posture": poor,
                "nose_point": (
                    float(nose.x),
                    float(nose.y),
                ),
                "left_shoulder_point": (
                    float(left_shoulder.x),
                    float(left_shoulder.y),
                ),
                "right_shoulder_point": (
                    float(right_shoulder.x),
                    float(right_shoulder.y),
                ),
                "landmarks": landmark_points,
                "timestamp": timestamp,
            },
        )

    def _reset_state(self) -> None:
        self.last_state = "UNKNOWN"
        self.last_score = 0.0
        self.last_confidence = 0.0
        self.last_tilt = 0.0
        self.last_head_forward = 0.0
        self.last_lean = 0.0

    def close(self) -> None:
        if self._pose is not None:
            try:
                self._pose.close()
            except Exception:
                pass

            self._pose = None
            self.available = False

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass