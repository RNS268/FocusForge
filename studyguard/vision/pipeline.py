from __future__ import annotations

import time
from typing import Any, Callable

from studyguard.core.config import DetectionSettings
from studyguard.vision.eye_detector import EyeDetector
from studyguard.vision.face_detector import FaceDetector
from studyguard.vision.hand_detector import HandDetector
from studyguard.vision.head_pose import AttentionDetector
from studyguard.vision.phone_detector import PhoneDetector
from studyguard.vision.posture_detector import PostureDetector
from studyguard.vision.presence_detector import PresenceDetector
from studyguard.vision.results import DetectionResult
from studyguard.vision.yawn_detector import YawnDetector


class VisionPipeline:
    """
    Coordinates all real-time computer-vision detectors.

    Face landmarks are intentionally calculated only once per frame and
    shared between detectors that depend on facial landmarks:

        FaceDetector
            ├── PresenceDetector
            ├── EyeDetector
            ├── AttentionDetector
            └── YawnDetector

    Other detectors continue to process the frame independently:

        HandDetector
        PhoneDetector
        PostureDetector

    This keeps the current detector interfaces intact while avoiding four
    separate MediaPipe FaceMesh inference passes for every camera frame.
    """

    def __init__(self, settings: DetectionSettings):
        self.settings = settings

        # Shared face detector. Several detectors depend on this instance.
        self.face = FaceDetector()

        # Preserve the original landmark implementation so that the pipeline
        # can temporarily serve one cached result to all face-based detectors.
        self._face_landmarks_impl: Callable[
            [Any], tuple[list[tuple[float, float, float]], float]
        ] = self.face.landmarks

        self._cached_face_landmarks: tuple[
            list[tuple[float, float, float]], float
        ] | None = None

        self._face_cache_active = False

        # Install a lightweight cache-aware wrapper on the shared FaceDetector.
        #
        # Existing detectors already call:
        #
        #     self.face.landmarks(frame)
        #
        # so this lets us optimize the pipeline without changing their public
        # interfaces in this file.
        self.face.landmarks = self._cached_face_landmarks_provider  # type: ignore[method-assign]

        self.presence = PresenceDetector(self.face)
        self.eyes = EyeDetector(self.face, settings)
        self.attention = AttentionDetector(self.face, settings)
        self.yawn = YawnDetector(self.face, settings)

        self.hands = HandDetector()
        self.phone = PhoneDetector(settings)
        self.posture = PostureDetector()

        # Keep a deterministic order. Face-dependent detectors run together
        # after the shared landmark calculation.
        self.detectors = [
            self.presence,
            self.eyes,
            self.attention,
            self.yawn,
            self.hands,
            self.phone,
            self.posture,
        ]

        self.last_latency_ms = 0.0
        self.last_timestamp: float | None = None

        # Useful runtime information for the UI/debug HUD.
        self.last_face_confidence = 0.0
        self.last_face_landmark_count = 0

        # Number of successful/failed processing cycles.
        self.frames_processed = 0
        self.processing_errors = 0

    def _cached_face_landmarks_provider(
        self,
        frame: Any,
    ) -> tuple[list[tuple[float, float, float]], float]:
        """
        Return the shared face-landmark result while the pipeline is processing
        a frame.

        Outside an active pipeline cycle, fall back to the real FaceDetector
        implementation so the FaceDetector remains usable independently.
        """
        if self._face_cache_active and self._cached_face_landmarks is not None:
            return self._cached_face_landmarks

        return self._face_landmarks_impl(frame)

    def _detect_face_once(self, frame: Any) -> None:
        """
        Run FaceMesh exactly once for the current frame and cache the result.
        """
        self._cached_face_landmarks = self._face_landmarks_impl(frame)

        landmarks, confidence = self._cached_face_landmarks
        self.last_face_confidence = confidence
        self.last_face_landmark_count = len(landmarks)

    def process(self, frame: Any, timestamp: float) -> list[DetectionResult]:
        """
        Process one camera frame through the complete vision pipeline.

        Face landmarks are calculated once and reused by all face-dependent
        detectors for this frame.
        """
        started = time.perf_counter()
        self.last_timestamp = timestamp

        results: list[DetectionResult] = []

        try:
            # -------------------------------------------------------------
            # 1. Calculate facial landmarks exactly once.
            # -------------------------------------------------------------
            self._detect_face_once(frame)

            # Enable shared-face cache for all detectors below.
            self._face_cache_active = True

            # -------------------------------------------------------------
            # 2. Run detectors.
            #
            # Presence / eyes / attention / yawn all reuse the same
            # FaceMesh result.
            #
            # Hand / phone / posture perform their own processing.
            # -------------------------------------------------------------
            for detector in self.detectors:
                try:
                    result = detector.process(frame, timestamp)

                    if result is not None:
                        results.append(result)

                except Exception:
                    # One detector should never bring down the complete
                    # webcam pipeline.
                    self.processing_errors += 1

                    # Keep the failure visible to the caller/UI rather than
                    # silently hiding it.
                    results.append(
                        DetectionResult(
                            name=getattr(detector, "name", "unknown"),
                            detected=False,
                            confidence=0.0,
                            event_type=None,
                            severity="info",
                            metadata={
                                "error": True,
                                "detector_failed": True,
                            },
                        )
                    )

        finally:
            # Never allow cached landmarks from one frame to leak into the
            # next frame.
            self._face_cache_active = False
            self._cached_face_landmarks = None

            self.last_latency_ms = (time.perf_counter() - started) * 1000.0
            self.frames_processed += 1

        return results

    @property
    def face_available(self) -> bool:
        """Whether the MediaPipe face detector is available."""
        return bool(self.face.available)

    @property
    def phone_available(self) -> bool:
        """Whether the local phone-detection model is available."""
        return bool(self.phone.available)

    @property
    def hands_available(self) -> bool:
        """Whether MediaPipe hand detection is available."""
        return bool(self.hands.available)

    @property
    def posture_available(self) -> bool:
        """Whether MediaPipe pose detection is available."""
        return bool(self.posture.available)

    def status(self) -> dict[str, Any]:
        """
        Return lightweight runtime information for the futuristic developer
        HUD / diagnostics panel.
        """
        return {
            "face_available": self.face_available,
            "phone_available": self.phone_available,
            "hands_available": self.hands_available,
            "posture_available": self.posture_available,
            "face_confidence": self.last_face_confidence,
            "face_landmarks": self.last_face_landmark_count,
            "latency_ms": self.last_latency_ms,
            "frames_processed": self.frames_processed,
            "processing_errors": self.processing_errors,
        }