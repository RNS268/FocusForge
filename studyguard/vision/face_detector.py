from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from studyguard.vision.base import BaseDetector
from studyguard.vision.results import DetectionResult


logger = logging.getLogger(__name__)


class FaceDetector(BaseDetector):
    """
    MediaPipe Tasks Face Landmarker detector.

    This replaces the old:

        mp.solutions.face_mesh.FaceMesh

    implementation.

    The rest of StudyGuard expects FaceDetector.landmarks() to return:

        list[(x, y, z)], confidence

    where x/y are normalized coordinates in the range 0..1.

    The MediaPipe Tasks Face Landmarker output is converted into that
    exact format so the existing PresenceDetector, EyeDetector,
    AttentionDetector and YawnDetector can continue using their existing
    landmark indexes.
    """

    name = "face"

    # MediaPipe Face Landmarker provides the dense face mesh used by the
    # existing detectors. The model can provide 478 landmarks when
    # iris refinement is available.
    MIN_LANDMARKS = 468

    MODEL_PATHS = (
        Path("models/face_landmarker.task"),
        Path("assets/models/face_landmarker.task"),
    )

    def __init__(self) -> None:
        self.available = False

        self._landmarker: Any = None
        self._mp: Any = None
        self._mp_image: Any = None

        self.model_path: str | None = None
        self.last_error: str | None = None

        self.last_landmarks: list[
            tuple[float, float, float]
        ] = []

        self.last_confidence = 0.0

        self.frames_processed = 0
        self.frames_with_face = 0
        self.frames_without_face = 0

        self._initialize()

    # ------------------------------------------------------------------
    # INITIALIZATION
    # ------------------------------------------------------------------

    def _initialize(self) -> None:
        """
        Initialize MediaPipe Tasks FaceLandmarker.
        """

        # --------------------------------------------------------------
        # Find local model.
        # --------------------------------------------------------------

        model_path = next(
            (
                path
                for path in self.MODEL_PATHS
                if path.exists()
            ),
            None,
        )

        if model_path is None:
            self._disable(
                "Face Landmarker model not found. Expected one of: "
                + ", ".join(
                    str(path)
                    for path in self.MODEL_PATHS
                )
            )
            return

        if model_path.stat().st_size <= 0:
            self._disable(
                f"Face Landmarker model is empty: {model_path}"
            )
            return

        self.model_path = str(model_path)

        # --------------------------------------------------------------
        # Import MediaPipe Tasks API.
        # --------------------------------------------------------------

        try:
            import mediapipe as mp

            self._mp = mp

            version = getattr(
                mp,
                "__version__",
                "unknown",
            )

            logger.info(
                "Initializing MediaPipe Tasks Face Landmarker: "
                "mediapipe=%s model=%s",
                version,
                model_path,
            )

        except Exception as exc:
            self._disable(
                f"Could not import mediapipe: {exc}"
            )
            return

        # --------------------------------------------------------------
        # Verify Tasks API.
        # --------------------------------------------------------------

        try:
            tasks = getattr(
                self._mp,
                "tasks",
                None,
            )

            if tasks is None:
                raise RuntimeError(
                    "mediapipe.tasks is unavailable"
                )

            vision = getattr(
                tasks,
                "vision",
                None,
            )

            if vision is None:
                raise RuntimeError(
                    "mediapipe.tasks.vision is unavailable"
                )

            face_landmarker_class = getattr(
                vision,
                "FaceLandmarker",
                None,
            )

            face_landmarker_options_class = getattr(
                vision,
                "FaceLandmarkerOptions",
                None,
            )

            running_mode_class = getattr(
                vision,
                "RunningMode",
                None,
            )

            if face_landmarker_class is None:
                raise RuntimeError(
                    "mediapipe.tasks.vision.FaceLandmarker "
                    "is unavailable"
                )

            if face_landmarker_options_class is None:
                raise RuntimeError(
                    "mediapipe.tasks.vision.FaceLandmarkerOptions "
                    "is unavailable"
                )

            if running_mode_class is None:
                raise RuntimeError(
                    "mediapipe.tasks.vision.RunningMode "
                    "is unavailable"
                )

        except Exception as exc:
            self._disable(
                f"MediaPipe Tasks API unavailable: {exc}"
            )
            return

        # --------------------------------------------------------------
        # Base options.
        # --------------------------------------------------------------

        try:
            base_options_class = getattr(
                tasks,
                "BaseOptions",
                None,
            )

            if base_options_class is None:
                raise RuntimeError(
                    "mediapipe.tasks.BaseOptions is unavailable"
                )

            base_options = base_options_class(
                model_asset_path=str(
                    model_path.resolve()
                )
            )

        except Exception as exc:
            self._disable(
                f"Could not create MediaPipe BaseOptions: {exc}"
            )
            return

        # --------------------------------------------------------------
        # Create FaceLandmarker.
        #
        # We deliberately use IMAGE mode.
        #
        # StudyGuard's pipeline already calls detectors synchronously
        # once per camera frame. Using detect() keeps the detector's
        # return value immediately available to the pipeline and avoids
        # introducing asynchronous result propagation into the existing
        # architecture.
        # --------------------------------------------------------------

        try:
            image_mode = getattr(
                running_mode_class,
                "IMAGE",
                None,
            )

            if image_mode is None:
                raise RuntimeError(
                    "MediaPipe RunningMode.IMAGE is unavailable"
                )

            options = face_landmarker_options_class(
                base_options=base_options,
                running_mode=image_mode,
                num_faces=1,
                min_face_detection_confidence=0.50,
                min_face_presence_confidence=0.50,
                min_tracking_confidence=0.50,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
            )

            self._landmarker = (
                face_landmarker_class.create_from_options(
                    options
                )
            )

            if self._landmarker is None:
                raise RuntimeError(
                    "FaceLandmarker.create_from_options() "
                    "returned None"
                )

            self.available = True
            self.last_error = None

            logger.info(
                "MediaPipe Tasks Face Landmarker initialized "
                "successfully: %s",
                model_path,
            )

        except Exception as exc:
            self._landmarker = None

            self._disable(
                f"Could not initialize MediaPipe Face Landmarker: "
                f"{exc}"
            )

    def _disable(
        self,
        reason: str,
    ) -> None:
        self.available = False
        self._landmarker = None
        self.last_error = reason

        logger.error(
            "Face detector disabled: %s",
            reason,
        )

    # ------------------------------------------------------------------
    # LANDMARKS
    # ------------------------------------------------------------------

    def landmarks(
        self,
        frame: Any,
    ) -> tuple[
        list[tuple[float, float, float]],
        float,
    ]:
        """
        Detect face landmarks from one OpenCV BGR frame.

        Returns:

            (
                [
                    (x, y, z),
                    ...
                ],
                confidence
            )

        Coordinates remain normalized exactly as expected by the
        existing eye/head/yawn detectors.
        """

        if (
            not self.available
            or self._landmarker is None
            or self._mp is None
        ):
            self._reset_current_detection()
            return [], 0.0

        if frame is None:
            self._reset_current_detection()
            return [], 0.0

        self.frames_processed += 1

        # --------------------------------------------------------------
        # Validate frame.
        # --------------------------------------------------------------

        try:
            if not hasattr(frame, "shape"):
                raise ValueError(
                    "Camera frame has no shape attribute"
                )

            shape = frame.shape

            if len(shape) < 2:
                raise ValueError(
                    f"Invalid camera frame shape: {shape}"
                )

            height = int(shape[0])
            width = int(shape[1])

            if width <= 0 or height <= 0:
                raise ValueError(
                    f"Invalid camera frame dimensions: "
                    f"{width}x{height}"
                )

        except Exception as exc:
            self._handle_processing_error(
                f"Invalid camera frame: {exc}"
            )
            return [], 0.0

        # --------------------------------------------------------------
        # Convert BGR -> RGB.
        # --------------------------------------------------------------

        try:
            import cv2

            rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB,
            )

        except Exception as exc:
            self._handle_processing_error(
                f"OpenCV BGR->RGB conversion failed: {exc}"
            )
            return [], 0.0

        # --------------------------------------------------------------
        # Create MediaPipe Image.
        # --------------------------------------------------------------

        try:
            image_format = getattr(
                self._mp.ImageFormat,
                "SRGB",
            )

            mp_image = self._mp.Image(
                image_format=image_format,
                data=rgb,
            )

        except Exception as exc:
            self._handle_processing_error(
                f"Could not create MediaPipe Image: {exc}"
            )
            return [], 0.0

        # --------------------------------------------------------------
        # Run Face Landmarker.
        # --------------------------------------------------------------

        try:
            result = self._landmarker.detect(
                mp_image
            )

        except Exception as exc:
            self._handle_processing_error(
                f"Face Landmarker detection failed: {exc}"
            )
            return [], 0.0

        # --------------------------------------------------------------
        # Extract face landmarks.
        # --------------------------------------------------------------

        try:
            face_landmarks = getattr(
                result,
                "face_landmarks",
                None,
            )

            if not face_landmarks:
                self.last_landmarks = []
                self.last_confidence = 0.0

                self.frames_without_face += 1

                return [], 0.0

            first_face = face_landmarks[0]

            if not first_face:
                self.last_landmarks = []
                self.last_confidence = 0.0

                self.frames_without_face += 1

                return [], 0.0

        except Exception as exc:
            self._handle_processing_error(
                f"Could not read Face Landmarker result: {exc}"
            )
            return [], 0.0

        # --------------------------------------------------------------
        # Convert Tasks landmarks to the format expected by StudyGuard.
        # --------------------------------------------------------------

        marks: list[
            tuple[float, float, float]
        ] = []

        try:
            for landmark in first_face:
                x = float(
                    getattr(
                        landmark,
                        "x",
                        0.0,
                    )
                )

                y = float(
                    getattr(
                        landmark,
                        "y",
                        0.0,
                    )
                )

                z = float(
                    getattr(
                        landmark,
                        "z",
                        0.0,
                    )
                )

                marks.append(
                    (
                        x,
                        y,
                        z,
                    )
                )

        except Exception as exc:
            self._handle_processing_error(
                f"Could not convert face landmarks: {exc}"
            )
            return [], 0.0

        # --------------------------------------------------------------
        # Validate landmarks.
        # --------------------------------------------------------------

        if len(marks) < self.MIN_LANDMARKS:
            self.last_landmarks = []
            self.last_confidence = 0.0

            self.frames_without_face += 1

            logger.warning(
                "Face Landmarker returned only %d landmarks; "
                "expected at least %d.",
                len(marks),
                self.MIN_LANDMARKS,
            )

            return [], 0.0

        # --------------------------------------------------------------
        # Face Landmarker provides face presence/detection confidence
        # internally but the basic result does not expose a single
        # FaceMesh-style confidence value.
        #
        # We therefore use a stable successful-detection confidence.
        # Presence/attention/etc. should rely on the landmark result
        # rather than pretending this is a detector probability.
        # --------------------------------------------------------------

        confidence = 0.90

        self.last_landmarks = marks
        self.last_confidence = confidence
        self.last_error = None

        self.frames_with_face += 1

        return marks, confidence

    # ------------------------------------------------------------------
    # DETECTION RESULT
    # ------------------------------------------------------------------

    def process(
        self,
        frame: Any,
        timestamp: float,
    ) -> DetectionResult:
        marks, confidence = self.landmarks(frame)

        detected = bool(marks)

        return DetectionResult(
            name=self.name,
            detected=detected,
            confidence=confidence,
            event_type=None,
            severity="info",
            metadata={
                "landmark_count": len(marks),
                "face_present": detected,
                "face_visible": detected,
                "available": self.available,
                "face_confidence": confidence,
                "model_path": self.model_path,
                "last_error": self.last_error,
                "frames_processed": self.frames_processed,
                "frames_with_face": self.frames_with_face,
                "frames_without_face": self.frames_without_face,
                "timestamp": timestamp,
            },
        )

    # ------------------------------------------------------------------
    # STATE
    # ------------------------------------------------------------------

    def _reset_current_detection(self) -> None:
        self.last_landmarks = []
        self.last_confidence = 0.0

    def _handle_processing_error(
        self,
        message: str,
    ) -> None:
        self.last_landmarks = []
        self.last_confidence = 0.0
        self.last_error = message

        logger.warning(
            "Face detector frame error: %s",
            message,
        )

    @property
    def face_detected(self) -> bool:
        return bool(self.last_landmarks)

    @property
    def landmark_count(self) -> int:
        return len(self.last_landmarks)

    @property
    def model_loaded(self) -> bool:
        return (
            self.available
            and self._landmarker is not None
        )

    def reset(self) -> None:
        self.last_landmarks = []
        self.last_confidence = 0.0
        self.last_error = None

        self.frames_processed = 0
        self.frames_with_face = 0
        self.frames_without_face = 0

    # ------------------------------------------------------------------
    # CLEANUP
    # ------------------------------------------------------------------

    def close(self) -> None:
        if self._landmarker is not None:
            try:
                self._landmarker.close()
            except Exception as exc:
                logger.debug(
                    "Error closing MediaPipe Face Landmarker: %s",
                    exc,
                )

        self._landmarker = None
        self.available = False

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass