# studyguard/core/camera.py

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from studyguard.core.config import CameraSettings

logger = logging.getLogger(__name__)


@dataclass
class FramePacket:
    frame: Any
    timestamp: float
    fps: float
    mock: bool = False


class CameraWorker:
    """Thread-safe camera capture worker with mock fallback."""

    def __init__(self, settings: CameraSettings):
        self.settings = settings

        self.running = False
        self.timer_only = False

        self.on_frame: Callable[[FramePacket], None] | None = None
        self.on_error: Callable[[str], None] | None = None

        self._capture: Any = None
        self._last_ts = time.monotonic()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        """
        Start camera capture without blocking the Qt GUI thread.
        """
        if self.running:
            return

        self.running = True
        self.timer_only = False
        self._stop_event.clear()
        self._last_ts = time.monotonic()

        self._thread = threading.Thread(
            target=self._capture_loop,
            name="StudyGuard-Camera",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """
        Stop capture and release the camera safely.
        """
        self.running = False
        self._stop_event.set()

        with self._lock:
            capture = self._capture
            self._capture = None

        if capture is not None:
            try:
                capture.release()
            except Exception:
                logger.exception("Failed to release camera")

        thread = self._thread

        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=2.0)

        self._thread = None

    def _capture_loop(self) -> None:
        """
        Camera loop running independently of the GUI thread.
        """
        try:
            self._open_camera()
        except Exception as exc:
            logger.warning(
                "Camera unavailable, entering mock mode: %s",
                exc,
            )

            self.timer_only = True

            if self.on_error:
                try:
                    self.on_error(str(exc))
                except Exception:
                    logger.exception(
                        "Camera error callback failed"
                    )

        target_fps = max(
            5.0,
            float(getattr(self.settings, "fps", 30)),
        )

        target_delay = 1.0 / target_fps

        while (
            self.running
            and not self._stop_event.is_set()
        ):
            loop_started = time.monotonic()

            try:
                packet = self._read_packet()

                if self.on_frame:
                    self.on_frame(packet)

            except Exception as exc:
                logger.exception(
                    "Camera processing failed"
                )

                if self.on_error:
                    try:
                        self.on_error(str(exc))
                    except Exception:
                        logger.exception(
                            "Camera error callback failed"
                        )

                if not self.timer_only:
                    self._switch_to_mock()

            elapsed = time.monotonic() - loop_started
            remaining = max(
                0.0,
                target_delay - elapsed,
            )

            if remaining > 0:
                self._stop_event.wait(remaining)

        self._release_capture()

    def _open_camera(self) -> None:
        import cv2

        index = int(
            getattr(
                self.settings,
                "index",
                0,
            )
        )

        capture = None

        # CAP_DSHOW is useful on Windows but may fail on some systems.
        # Try it first, then fall back to the default OpenCV backend.
        try:
            capture = cv2.VideoCapture(
                index,
                cv2.CAP_DSHOW,
            )
        except Exception:
            capture = None

        if capture is None or not capture.isOpened():
            if capture is not None:
                try:
                    capture.release()
                except Exception:
                    pass

            capture = cv2.VideoCapture(index)

        if capture is None or not capture.isOpened():
            raise RuntimeError(
                f"Camera {index} is unavailable"
            )

        width = int(
            getattr(
                self.settings,
                "width",
                1280,
            )
        )

        height = int(
            getattr(
                self.settings,
                "height",
                720,
            )
        )

        fps = float(
            getattr(
                self.settings,
                "fps",
                30,
            )
        )

        capture.set(
            cv2.CAP_PROP_FRAME_WIDTH,
            width,
        )

        capture.set(
            cv2.CAP_PROP_FRAME_HEIGHT,
            height,
        )

        capture.set(
            cv2.CAP_PROP_FPS,
            fps,
        )

        with self._lock:
            self._capture = capture

        self.timer_only = False

        logger.info(
            "Camera started: index=%s resolution=%sx%s fps=%s",
            index,
            width,
            height,
            fps,
        )

    def _read_packet(self) -> FramePacket:
        now = time.monotonic()

        fps = 1.0 / max(
            now - self._last_ts,
            1e-6,
        )

        # Prevent meaningless FPS spikes from appearing in the HUD.
        fps = min(
            fps,
            max(
                5.0,
                float(
                    getattr(
                        self.settings,
                        "fps",
                        30,
                    )
                )
                * 2.0,
            ),
        )

        self._last_ts = now

        with self._lock:
            capture = self._capture

        if (
            self.timer_only
            or capture is None
        ):
            return FramePacket(
                frame=self._mock_frame(now),
                timestamp=now,
                fps=fps,
                mock=True,
            )

        ok, frame = capture.read()

        if not ok or frame is None:
            logger.warning(
                "Camera frame read failed, switching to mock mode"
            )

            self._switch_to_mock()

            return FramePacket(
                frame=self._mock_frame(now),
                timestamp=now,
                fps=fps,
                mock=True,
            )

        try:
            import cv2

            if bool(
                getattr(
                    self.settings,
                    "mirror",
                    True,
                )
            ):
                frame = cv2.flip(
                    frame,
                    1,
                )

        except Exception:
            logger.debug(
                "Could not mirror camera frame",
                exc_info=True,
            )

        return FramePacket(
            frame=frame,
            timestamp=now,
            fps=fps,
            mock=False,
        )

    def _switch_to_mock(self) -> None:
        self.timer_only = True
        self._release_capture()

    def _release_capture(self) -> None:
        with self._lock:
            capture = self._capture
            self._capture = None

        if capture is not None:
            try:
                capture.release()
            except Exception:
                logger.debug(
                    "Camera release failed",
                    exc_info=True,
                )

    def _mock_frame(
        self,
        timestamp: float,
    ) -> Any:
        """
        Generate an animated futuristic fallback frame.

        This keeps the application's dashboard and timer usable even when
        the camera is unavailable.
        """
        import numpy as np

        width = int(
            getattr(
                self.settings,
                "width",
                1280,
            )
        )

        height = int(
            getattr(
                self.settings,
                "height",
                720,
            )
        )

        width = max(320, width)
        height = max(240, height)

        frame = np.zeros(
            (height, width, 3),
            dtype=np.uint8,
        )

        pulse = int(
            40
            + 30
            * math.sin(
                timestamp * 2.0
            )
        )

        frame[:, :] = (
            18,
            22 + pulse // 5,
            28 + pulse // 3,
        )

        cx = int(
            width / 2
            + math.sin(timestamp) * 40
        )

        cy = height // 2

        try:
            import cv2

            # Main face/HUD circle.
            cv2.circle(
                frame,
                (cx, cy),
                120,
                (80, 210, 210),
                2,
            )

            # Animated eye indicators.
            eye_pulse = int(
                8
                + 4
                * (
                    1
                    + math.sin(
                        timestamp * 3.0
                    )
                )
            )

            cv2.circle(
                frame,
                (cx - 45, cy - 25),
                eye_pulse,
                (160, 255, 230),
                -1,
            )

            cv2.circle(
                frame,
                (cx + 45, cy - 25),
                eye_pulse,
                (160, 255, 230),
                -1,
            )

            cv2.ellipse(
                frame,
                (cx, cy + 45),
                (45, 18),
                0,
                0,
                180,
                (160, 255, 230),
                2,
            )

            cv2.putText(
                frame,
                "STUDYGUARD AI",
                (32, 42),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (120, 240, 240),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                frame,
                "CAMERA OFFLINE",
                (32, 76),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (100, 190, 210),
                1,
                cv2.LINE_AA,
            )

            cv2.putText(
                frame,
                "TIMER / ANALYTICS MODE",
                (32, height - 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (120, 240, 240),
                1,
                cv2.LINE_AA,
            )

            # Futuristic scanning line.
            scan_y = int(
                (
                    timestamp * 90
                )
                % max(
                    height,
                    1,
                )
            )

            cv2.line(
                frame,
                (0, scan_y),
                (width, scan_y),
                (70, 150, 160),
                1,
                cv2.LINE_AA,
            )

        except Exception:
            pass

        return frame