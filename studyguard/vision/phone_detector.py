# studyguard/vision/phone_detector.py

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from studyguard.core.config import DetectionSettings
from studyguard.vision.base import BaseDetector
from studyguard.vision.results import DetectionResult

logger = logging.getLogger(__name__)


class PhoneDetector(BaseDetector):
    """
    Local YOLO-based phone detector.

    Behavior:
    - Uses only a locally available YOLO model.
    - Never downloads weights automatically.
    - Detects phone-related YOLO classes.
    - Runs YOLO periodically to reduce CPU usage.
    - Keeps the latest confirmed detection visible between inference frames.
    - Keeps a detection briefly across missed YOLO inference cycles.
    - Clears the detection once the persistence period expires.
    """

    name = "phone"

    MODEL_PATHS = (
        Path("models/yolov8n.pt"),
        Path("models/yolo11n.pt"),
        Path("assets/models/yolo11n.pt"),
    )

    PHONE_CLASSES = {
        "cell phone",
        "mobile phone",
        "phone",
        "smartphone",
    }

    def __init__(
        self,
        settings: DetectionSettings | None = None,
    ) -> None:
        self.settings = settings

        self.model: Any = None
        self.names: dict[Any, Any] = {}

        self.available = False
        self.model_path: str | None = None

        # Camera frame counter.
        self.frame_count = 0

        # Run YOLO every N camera frames.
        #
        # At 30 FPS and interval=3, YOLO runs approximately 10 times/sec.
        # This is substantially more responsive than the previous 6.
        self.inference_interval = 3

        # Last confirmed phone detection.
        self.last_box: tuple[int, int, int, int] | None = None
        self.last_confidence = 0.0

        # Number of consecutive YOLO inference misses for which the
        # previous detection is retained.
        self.persistence_frames = max(
            1,
            int(
                getattr(
                    settings,
                    "phone_persistence_frames",
                    2,
                )
                if settings is not None
                else 2
            ),
        )

        # Counts missed YOLO inference cycles.
        self._stale_frames = 0

        self._load_model()

    # ------------------------------------------------------------------
    # MODEL
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        model_path = next(
            (
                path
                for path in self.MODEL_PATHS
                if path.exists()
            ),
            None,
        )

        if model_path is None:
            logger.info(
                "Phone detection disabled: no local YOLO model found. "
                "Expected one of: %s",
                ", ".join(
                    str(path)
                    for path in self.MODEL_PATHS
                ),
            )
            return

        try:
            from ultralytics import YOLO

            self.model = YOLO(str(model_path))

            raw_names = getattr(
                self.model,
                "names",
                {},
            )

            if isinstance(raw_names, dict):
                self.names = raw_names

            elif isinstance(raw_names, list):
                self.names = {
                    index: name
                    for index, name in enumerate(raw_names)
                }

            else:
                self.names = {}

            self.available = True
            self.model_path = str(model_path)

            logger.info(
                "Phone detector loaded: %s",
                model_path,
            )

            logger.info(
                "Phone detector classes: %s",
                self.names,
            )

        except Exception as exc:
            self.model = None
            self.available = False
            self.names = {}
            self.model_path = None

            logger.warning(
                "Could not load YOLO phone model %s: %s",
                model_path,
                exc,
            )

    # ------------------------------------------------------------------
    # DETECTION
    # ------------------------------------------------------------------

    def process(
        self,
        frame: Any,
        timestamp: float,
    ) -> DetectionResult:
        """
        Detect a phone in the supplied frame.

        YOLO does not need to run on every camera frame.

        Example at 30 FPS:

            frame 1 -> use previous state
            frame 2 -> use previous state
            frame 3 -> YOLO
            frame 4 -> use latest YOLO state
            frame 5 -> use latest YOLO state
            frame 6 -> YOLO
            ...

        A confirmed phone therefore remains visible on the HUD between
        inference frames.
        """

        if (
            not self.available
            or self.model is None
        ):
            return self._result(
                detected=False,
                confidence=0.0,
                inference=False,
                timestamp=timestamp,
            )

        self.frame_count += 1

        # --------------------------------------------------------------
        # INTERMEDIATE CAMERA FRAME
        # --------------------------------------------------------------

        if (
            self.frame_count
            % self.inference_interval
            != 0
        ):
            if self.last_box is not None:
                return self._result(
                    detected=True,
                    confidence=self.last_confidence,
                    inference=False,
                    timestamp=timestamp,
                )

            return self._result(
                detected=False,
                confidence=0.0,
                inference=False,
                timestamp=timestamp,
            )

        # --------------------------------------------------------------
        # YOLO INFERENCE
        # --------------------------------------------------------------

        confidence_threshold = (
            float(
                getattr(
                    self.settings,
                    "phone_confidence",
                    0.45,
                )
            )
            if self.settings is not None
            else 0.45
        )

        # Keep this inside safe bounds.
        confidence_threshold = max(
            0.05,
            min(
                0.95,
                confidence_threshold,
            ),
        )

        try:
            results = self.model.predict(
                frame,
                verbose=False,
                conf=confidence_threshold,
                imgsz=640,
                device="cpu",
                max_det=10,
            )

        except Exception as exc:
            logger.warning(
                "Phone detector inference failed: %s",
                exc,
            )

            self._stale_frames += 1

            if (
                self.last_box is not None
                and self._stale_frames
                <= self.persistence_frames
            ):
                return self._result(
                    detected=True,
                    confidence=self.last_confidence,
                    inference=True,
                    timestamp=timestamp,
                )

            self._clear_detection()

            return self._result(
                detected=False,
                confidence=0.0,
                inference=True,
                timestamp=timestamp,
            )

        # --------------------------------------------------------------
        # FIND BEST PHONE
        # --------------------------------------------------------------

        best_confidence = 0.0
        best_box: tuple[int, int, int, int] | None = None

        for result in results:
            boxes = getattr(
                result,
                "boxes",
                None,
            )

            if boxes is None:
                continue

            for box in boxes:
                try:
                    cls_id = int(
                        box.cls[0]
                    )

                    confidence = float(
                        box.conf[0]
                    )

                    class_name = str(
                        self.names.get(
                            cls_id,
                            "",
                        )
                    ).strip().lower()

                    # Only accept actual phone classes.
                    if class_name not in self.PHONE_CLASSES:
                        continue

                    if confidence < best_confidence:
                        continue

                    coordinates = (
                        box.xyxy[0].tolist()
                    )

                    if len(coordinates) != 4:
                        continue

                    x1, y1, x2, y2 = (
                        int(value)
                        for value in coordinates
                    )

                    # Basic sanity check.
                    if x2 <= x1 or y2 <= y1:
                        continue

                    best_confidence = confidence
                    best_box = (
                        x1,
                        y1,
                        x2,
                        y2,
                    )

                except Exception:
                    continue

        # --------------------------------------------------------------
        # PHONE FOUND
        # --------------------------------------------------------------

        if best_box is not None:
            self.last_box = best_box
            self.last_confidence = best_confidence

            # A successful detection resets the missed-inference counter.
            self._stale_frames = 0

            return self._result(
                detected=True,
                confidence=best_confidence,
                inference=True,
                timestamp=timestamp,
            )

        # --------------------------------------------------------------
        # PHONE NOT FOUND
        # --------------------------------------------------------------

        self._stale_frames += 1

        # Do not immediately remove the phone after one missed YOLO
        # inference. This prevents flickering caused by one bad frame.
        if (
            self.last_box is not None
            and self._stale_frames
            <= self.persistence_frames
        ):
            return self._result(
                detected=True,
                confidence=self.last_confidence,
                inference=True,
                timestamp=timestamp,
            )

        # Persistence expired.
        self._clear_detection()

        return self._result(
            detected=False,
            confidence=0.0,
            inference=True,
            timestamp=timestamp,
        )

    # ------------------------------------------------------------------
    # RESULT
    # ------------------------------------------------------------------

    def _result(
        self,
        detected: bool,
        confidence: float,
        inference: bool,
        timestamp: float,
    ) -> DetectionResult:
        safe_confidence = max(
            0.0,
            min(
                1.0,
                float(confidence),
            ),
        )

        event_type = (
            "PHONE_DETECTED"
            if detected
            else None
        )

        return DetectionResult(
            name=self.name,
            detected=detected,
            confidence=safe_confidence,
            event_type=event_type,
            severity=(
                "warning"
                if detected
                else "info"
            ),
            metadata={
                "phone_confidence": safe_confidence,

                # IMPORTANT:
                # camera_view.py uses this for the live bounding box.
                "phone_box": self.last_box,

                "model_available": self.available,
                "model_path": self.model_path,

                # Debug/live pipeline information.
                "inference": inference,
                "frame_count": self.frame_count,
                "inference_interval": self.inference_interval,
                "stale_frames": self._stale_frames,
                "persistence_frames": self.persistence_frames,
                "timestamp": timestamp,
            },
        )

    # ------------------------------------------------------------------
    # STATE
    # ------------------------------------------------------------------

    def _clear_detection(self) -> None:
        self.last_box = None
        self.last_confidence = 0.0
        self._stale_frames = 0

    # ------------------------------------------------------------------
    # PUBLIC HELPERS
    # ------------------------------------------------------------------

    @property
    def model_loaded(self) -> bool:
        return (
            self.available
            and self.model is not None
        )

    @property
    def detected(self) -> bool:
        """
        Current live phone state.
        """
        return self.last_box is not None

    @property
    def confidence(self) -> float:
        """
        Current live phone confidence.
        """
        return self.last_confidence

    @property
    def bounding_box(
        self,
    ) -> tuple[int, int, int, int] | None:
        """
        Current live phone bounding box.
        """
        return self.last_box

    def reset(self) -> None:
        """
        Completely reset detector runtime state.
        """
        self.frame_count = 0
        self._clear_detection()

    def close(self) -> None:
        """
        Release the YOLO model.
        """
        self.model = None
        self.available = False
        self.names = {}
        self._clear_detection()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass