# studyguard/vision/hand_detector.py

from __future__ import annotations

from math import hypot
from typing import Any

from studyguard.vision.base import BaseDetector
from studyguard.vision.results import DetectionResult


class HandDetector(BaseDetector):
    name = "hands"

    WRIST = 0
    THUMB_TIP = 4
    INDEX_TIP = 8
    MIDDLE_TIP = 12
    RING_TIP = 16
    PINKY_TIP = 20

    FINGER_TIPS = (
        INDEX_TIP,
        MIDDLE_TIP,
        RING_TIP,
        PINKY_TIP,
    )

    def __init__(self) -> None:
        self.available = False
        self._hands = None

        self.last_count = 0
        self.last_confidence = 0.0
        self.last_points: list[list[tuple[float, float]]] = []
        self.last_handedness: list[str] = []
        self.last_hand_boxes: list[tuple[float, float, float, float]] = []

        try:
            import mediapipe as mp

            self._hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                model_complexity=0,
                min_detection_confidence=0.55,
                min_tracking_confidence=0.55,
            )
            self.available = True
        except Exception:
            self._hands = None
            self.available = False

    def process(
        self,
        frame: Any,
        timestamp: float,
    ) -> DetectionResult:
        if not self.available or self._hands is None:
            self._reset_runtime_state()

            return DetectionResult(
                self.name,
                False,
                0.0,
                metadata={
                    "available": False,
                    "hands": 0,
                    "hand_points": [],
                    "handedness": [],
                    "hand_boxes": [],
                    "hand_details": [],
                    "near_camera": False,
                    "near_face": False,
                },
            )

        try:
            import cv2

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self._hands.process(rgb)
        except Exception:
            self._reset_runtime_state()

            return DetectionResult(
                self.name,
                False,
                0.0,
                metadata={
                    "available": True,
                    "hands": 0,
                    "hand_points": [],
                    "handedness": [],
                    "hand_boxes": [],
                    "hand_details": [],
                    "near_camera": False,
                    "near_face": False,
                    "processing_error": True,
                },
            )

        hand_landmarks = results.multi_hand_landmarks or []
        handedness_results = results.multi_handedness or []

        count = len(hand_landmarks)

        points: list[list[tuple[float, float]]] = []
        handedness: list[str] = []
        boxes: list[tuple[float, float, float, float]] = []
        details: list[dict[str, Any]] = []

        frame_height, frame_width = frame.shape[:2]

        for index, hand in enumerate(hand_landmarks):
            hand_points = [
                (
                    max(0.0, min(1.0, float(lm.x))),
                    max(0.0, min(1.0, float(lm.y))),
                )
                for lm in hand.landmark
            ]

            points.append(hand_points)

            label = "UNKNOWN"
            hand_confidence = 0.0

            if index < len(handedness_results):
                classification = handedness_results[index].classification

                if classification:
                    label = str(
                        classification[0].label
                    ).upper()

                    hand_confidence = float(
                        classification[0].score
                    )

            handedness.append(label)

            xs = [point[0] for point in hand_points]
            ys = [point[1] for point in hand_points]

            if xs and ys:
                x1 = max(0.0, min(xs))
                y1 = max(0.0, min(ys))
                x2 = min(1.0, max(xs))
                y2 = min(1.0, max(ys))
            else:
                x1 = y1 = x2 = y2 = 0.0

            boxes.append((x1, y1, x2, y2))

            wrist = hand_points[self.WRIST]

            finger_distances = [
                self._distance_2d(
                    wrist,
                    hand_points[tip],
                )
                for tip in self.FINGER_TIPS
            ]

            palm_size = max(
                self._distance_2d(
                    hand_points[self.WRIST],
                    hand_points[self.MIDDLE_TIP],
                ),
                1e-6,
            )

            average_finger_distance = (
                sum(finger_distances)
                / len(finger_distances)
                if finger_distances
                else 0.0
            )

            # A large normalized hand size usually means the hand is close
            # to the camera. This is useful for detecting the "hand over
            # camera" behavior from the original project.
            hand_width = max(0.0, x2 - x1)
            hand_height = max(0.0, y2 - y1)
            hand_area = hand_width * hand_height

            near_camera = (
                hand_width >= 0.38
                or hand_height >= 0.55
                or hand_area >= 0.18
            )

            details.append(
                {
                    "index": index,
                    "label": label,
                    "confidence": hand_confidence,
                    "wrist": wrist,
                    "bbox": (x1, y1, x2, y2),
                    "width": hand_width,
                    "height": hand_height,
                    "area": hand_area,
                    "near_camera": near_camera,
                    "average_finger_distance": average_finger_distance,
                    "palm_size": palm_size,
                }
            )

        confidence = (
            min(1.0, count / 2.0)
            if count
            else 0.0
        )

        near_camera = any(
            detail["near_camera"]
            for detail in details
        )

        near_face = self._estimate_near_face(
            details,
            frame_width,
            frame_height,
        )

        self.last_count = count
        self.last_confidence = confidence
        self.last_points = points
        self.last_handedness = handedness
        self.last_hand_boxes = boxes

        return DetectionResult(
            self.name,
            count > 0,
            confidence,
            event_type=None,
            severity="info",
            metadata={
                "available": True,
                "hands": count,
                "hand_points": points,
                "handedness": handedness,
                "hand_boxes": boxes,
                "hand_details": details,
                "near_camera": near_camera,
                "near_face": near_face,
                "timestamp": timestamp,
            },
        )

    def _estimate_near_face(
        self,
        details: list[dict[str, Any]],
        frame_width: int,
        frame_height: int,
    ) -> bool:
        """
        Estimate whether a hand is in the upper/central region where the
        user's face normally appears.

        This is intentionally only a geometric signal. It does not generate
        a PHONE_DETECTED event by itself; the phone detector/event engine can
        combine this with phone detection later.
        """
        if not details:
            return False

        for detail in details:
            x1, y1, x2, y2 = detail["bbox"]

            center_x = (x1 + x2) / 2.0
            center_y = (y1 + y2) / 2.0

            if (
                0.20 <= center_x <= 0.80
                and 0.05 <= center_y <= 0.65
            ):
                return True

        return False

    @staticmethod
    def _distance_2d(
        first: tuple[float, float],
        second: tuple[float, float],
    ) -> float:
        return hypot(
            first[0] - second[0],
            first[1] - second[1],
        )

    def _reset_runtime_state(self) -> None:
        self.last_count = 0
        self.last_confidence = 0.0
        self.last_points = []
        self.last_handedness = []
        self.last_hand_boxes = []

    def close(self) -> None:
        """
        Release MediaPipe resources when the application shuts down.
        """
        if self._hands is not None:
            try:
                self._hands.close()
            except Exception:
                pass

            self._hands = None
            self.available = False

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass