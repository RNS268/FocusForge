# studyguard/ui/camera_view.py

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QRectF, Qt, QSize, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
    QPolygon,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from studyguard.core.camera import FramePacket


class CameraView(QWidget):
    retry_requested = Signal()
    select_requested = Signal()
    timer_only_requested = Signal()

    # Preferred camera aspect ratio: 1280x720.
    CAMERA_ASPECT = 16 / 9

    def __init__(self) -> None:
        super().__init__()

        self.setObjectName("StudyGuardCameraView")

        # --------------------------------------------------------------
        # IMPORTANT:
        # Make the camera area expand aggressively when the main window
        # has available vertical space.
        # --------------------------------------------------------------
        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        self.setMinimumSize(640, 360)

        self.frame_label = QLabel("CAMERA INITIALIZING")
        self.frame_label.setAlignment(Qt.AlignCenter)

        self.frame_label.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        self.frame_label.setStyleSheet(
            """
            QLabel {
                background: #05080d;
                border: 1px solid rgba(91, 209, 255, 0.28);
                border-radius: 10px;
                color: #7de7ff;
            }
            """
        )

        self.hud_data: dict[str, Any] = {}
        self._last_image: QImage | None = None

        # --------------------------------------------------------------
        # MAIN LAYOUT
        # --------------------------------------------------------------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # No unnecessary vertical spacing around the camera.
        layout.setSpacing(4)

        # Give the actual camera almost all available space.
        layout.addWidget(
            self.frame_label,
            100,
        )

        # --------------------------------------------------------------
        # CAMERA ERROR CONTROLS
        # --------------------------------------------------------------
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)

        self.retry_button = QPushButton("↻  Retry")
        self.select_button = QPushButton("▣  Select Camera")
        self.timer_button = QPushButton(
            "▶  Continue Timer-Only"
        )

        self.retry_button.clicked.connect(
            self.retry_requested.emit
        )

        self.select_button.clicked.connect(
            self.select_requested.emit
        )

        self.timer_button.clicked.connect(
            self.timer_only_requested.emit
        )

        for button in (
            self.retry_button,
            self.select_button,
            self.timer_button,
        ):
            button.setVisible(False)
            controls.addWidget(button)

        layout.addLayout(
            controls,
            0,
        )

        # --------------------------------------------------------------
        # Keep the camera itself dominant.
        # --------------------------------------------------------------
        layout.setStretch(
            0,
            100,
        )

        # Controls should consume essentially no space when hidden.
        layout.setStretch(
            1,
            0,
        )

    # ==================================================================
    # SIZE HINT
    # ==================================================================

    def sizeHint(self) -> QSize:
        """
        Tell Qt that the camera prefers a large 16:9 area.

        This helps parent layouts allocate more space to the camera
        instead of treating it like an ordinary small widget.
        """
        return QSize(
            1280,
            720,
        )

    def minimumSizeHint(self) -> QSize:
        return QSize(
            640,
            360,
        )

    # ==================================================================
    # PUBLIC API
    # ==================================================================

    def update_frame(
        self,
        packet: FramePacket,
        hud_data: dict[str, Any],
    ) -> None:
        """
        Update the live camera image and complete vision HUD.

        hud_data may contain:
            - EYES
            - HAND
            - PHONE_STATE
            - POSE
            - POSTURE
            - PRESENCE
            - FOCUS
            - CONFIDENCE
            - FPS
            - STATUS
            - WARNING

        Vision point data:
            - _eye_points
            - _eye_closed
            - _mouth_points
            - _yawning
            - _hand_points
            - _hand_near_camera
            - _phone_box
            - _source_size
            - _posture_points
        """

        self.hud_data = dict(
            hud_data or {}
        )

        image = self._to_image(
            packet.frame
        )

        if image.isNull():
            self.frame_label.clear()
            self.frame_label.setText(
                "INVALID CAMERA FRAME"
            )
            return

        self._last_image = image

        # --------------------------------------------------------------
        # Render to the CURRENT camera label size.
        #
        # This is important after the main window is resized.
        # --------------------------------------------------------------
        target_size = self.frame_label.size()

        if (
            target_size.width() > 0
            and target_size.height() > 0
        ):
            pixmap = QPixmap.fromImage(
                image
            ).scaled(
                target_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        else:
            pixmap = QPixmap.fromImage(
                image
            )

        painted = QPixmap(pixmap)

        painter = QPainter(
            painted
        )

        painter.setRenderHint(
            QPainter.Antialiasing,
            True,
        )

        painter.setRenderHint(
            QPainter.TextAntialiasing,
            True,
        )

        # --------------------------------------------------------------
        # Background futuristic grid / scan
        # --------------------------------------------------------------
        self._draw_scan_overlay(
            painter,
            painted.width(),
            painted.height(),
        )

        # --------------------------------------------------------------
        # Vision overlays
        # --------------------------------------------------------------
        self._draw_vision_marks(
            painter,
            painted.width(),
            painted.height(),
            self.hud_data,
        )

        # --------------------------------------------------------------
        # Main futuristic HUD
        # --------------------------------------------------------------
        self._draw_futuristic_hud(
            painter,
            painted.width(),
            painted.height(),
            packet,
            self.hud_data,
        )

        painter.end()

        self.frame_label.setPixmap(
            painted
        )

        self._set_controls_visible(
            False
        )

    # ==================================================================
    # CAMERA ERROR
    # ==================================================================

    def show_camera_error(
        self,
        message: str,
    ) -> None:
        self.frame_label.clear()

        self.frame_label.setText(
            "CAMERA UNAVAILABLE\n\n"
            f"{message}\n\n"
            "Retry, select another camera, "
            "or continue in timer-only mode."
        )

        self._set_controls_visible(
            True
        )

    # ==================================================================
    # RESIZE
    # ==================================================================

    def resizeEvent(
        self,
        event: Any,
    ) -> None:
        super().resizeEvent(
            event
        )

        self._refresh_last_frame()

    # ==================================================================
    # SHOW
    # ==================================================================

    def showEvent(
        self,
        event: Any,
    ) -> None:
        super().showEvent(
            event
        )

        # If a frame already exists, immediately redraw it using the
        # newly allocated camera area.
        self._refresh_last_frame()

    # ==================================================================
    # REFRESH LAST FRAME
    # ==================================================================

    def _refresh_last_frame(
        self,
    ) -> None:
        """
        Re-render the last camera frame after the widget changes size.

        This prevents the image from remaining at the old dimensions
        when the application window is resized/maximized.
        """

        if self._last_image is None:
            return

        target_size = self.frame_label.size()

        if (
            target_size.width() <= 0
            or target_size.height() <= 0
        ):
            return

        pixmap = QPixmap.fromImage(
            self._last_image
        ).scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        # Don't redraw HUD here because the normal camera worker will
        # provide the latest HUD data. This simply prevents a blank
        # camera during resizing.
        self.frame_label.setPixmap(
            pixmap
        )

    # ==================================================================
    # CONTROLS
    # ==================================================================

    def _set_controls_visible(
        self,
        visible: bool,
    ) -> None:
        for button in (
            self.retry_button,
            self.select_button,
            self.timer_button,
        ):
            button.setVisible(
                visible
            )

    # ==================================================================
    # IMAGE CONVERSION
    # ==================================================================

    def _to_image(
        self,
        frame: Any,
    ) -> QImage:

        try:
            import cv2

            rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB,
            )

        except Exception:
            rgb = frame

        if rgb is None:
            return QImage()

        try:
            height, width = rgb.shape[:2]

            # ----------------------------------------------------------
            # Grayscale
            # ----------------------------------------------------------
            if len(rgb.shape) == 2:
                return QImage(
                    rgb.data,
                    width,
                    height,
                    width,
                    QImage.Format_Grayscale8,
                ).copy()

            # ----------------------------------------------------------
            # RGBA
            # ----------------------------------------------------------
            channels = rgb.shape[2]

            if channels == 4:
                return QImage(
                    rgb.data,
                    width,
                    height,
                    width * 4,
                    QImage.Format_RGBA8888,
                ).copy()

            # ----------------------------------------------------------
            # RGB
            # ----------------------------------------------------------
            bytes_per_line = (
                3 * width
            )

            return QImage(
                rgb.data,
                width,
                height,
                bytes_per_line,
                QImage.Format_RGB888,
            ).copy()

        except Exception:
            return QImage()

    # ==================================================================
    # FUTURISTIC HUD
    # ==================================================================

    def _draw_futuristic_hud(
        self,
        painter: QPainter,
        width: int,
        height: int,
        packet: FramePacket,
        hud_data: dict[str, Any],
    ) -> None:

        eye_state = str(
            hud_data.get(
                "EYES",
                "OPEN",
            )
        ).upper()

        hand_state = str(
            hud_data.get(
                "HAND",
                "CLEAR",
            )
        ).upper()

        phone_state = str(
            hud_data.get(
                "PHONE_STATE",
                "CLEAR",
            )
        ).upper()

        pose = str(
            hud_data.get(
                "POSE",
                "CENTER",
            )
        ).upper()

        posture = str(
            hud_data.get(
                "POSTURE",
                "GOOD",
            )
        ).upper()

        presence = str(
            hud_data.get(
                "PRESENCE",
                "PRESENT",
            )
        ).upper()

        fps = self._safe_float(
            hud_data.get(
                "FPS",
                packet.fps,
            ),
            0.0,
        )

        confidence = self._safe_float(
            hud_data.get(
                "CONFIDENCE",
                0.0,
            ),
            0.0,
        )

        focus = self._safe_float(
            hud_data.get(
                "FOCUS",
                hud_data.get(
                    "FOCUS_PERCENTAGE",
                    0.0,
                ),
            ),
            0.0,
        )

        # Handle strings such as "100%".
        focus = min(
            100.0,
            max(
                0.0,
                focus,
            ),
        )

        # If confidence is supplied as percentage.
        if confidence > 1.0:
            confidence /= 100.0

        confidence = min(
            1.0,
            max(
                0.0,
                confidence,
            ),
        )

        # --------------------------------------------------------------
        # Camera border
        # --------------------------------------------------------------

        painter.setBrush(
            Qt.NoBrush
        )

        painter.setPen(
            QPen(
                QColor(
                    78,
                    220,
                    255,
                    150,
                ),
                1.5,
            )
        )

        painter.drawRoundedRect(
            QRectF(
                1,
                1,
                max(
                    1,
                    width - 3,
                ),
                max(
                    1,
                    height - 3,
                ),
            ),
            8,
            8,
        )

        # --------------------------------------------------------------
        # TOP LEFT
        # --------------------------------------------------------------

        top_left_width = min(
            245,
            max(
                220,
                width // 3,
            ),
        )

        top_left_height = 152

        painter.setPen(
            Qt.NoPen
        )

        painter.setBrush(
            QColor(
                4,
                10,
                18,
                205,
            )
        )

        painter.drawRoundedRect(
            QRectF(
                12,
                12,
                top_left_width,
                top_left_height,
            ),
            8,
            8,
        )

        painter.setPen(
            QPen(
                QColor("#4edcff"),
                1,
            )
        )

        painter.drawRoundedRect(
            QRectF(
                12,
                12,
                top_left_width,
                top_left_height,
            ),
            8,
            8,
        )

        painter.setFont(
            QFont(
                "Cascadia Mono",
                10,
                QFont.Bold,
            )
        )

        painter.setPen(
            QColor("#75eaff")
        )

        painter.drawText(
            24,
            34,
            "◈  STUDYGUARD // VISION",
        )

        painter.setFont(
            QFont(
                "Cascadia Mono",
                9,
            )
        )

        painter.setPen(
            QColor("#9bb7c8")
        )

        painter.drawText(
            24,
            57,
            f"CAM  {'MOCK' if packet.mock else 'LIVE'}",
        )

        painter.drawText(
            24,
            77,
            f"FPS  {fps:04.1f}",
        )

        painter.drawText(
            24,
            97,
            f"AI   {confidence * 100:03.0f}%",
        )

        painter.drawText(
            24,
            117,
            f"FOCUS {focus:03.0f}%",
        )

        status = str(
            hud_data.get(
                "STATUS",
                "MONITORING",
            )
        )

        painter.drawText(
            24,
            137,
            status[:26],
        )

        # --------------------------------------------------------------
        # RIGHT SYSTEM MONITOR
        # --------------------------------------------------------------

        panel_width = min(
            210,
            max(
                190,
                width // 4,
            ),
        )

        panel_height = 198

        panel_x = (
            width
            - panel_width
            - 12
        )

        panel_y = 12

        painter.setPen(
            Qt.NoPen
        )

        painter.setBrush(
            QColor(
                4,
                10,
                18,
                205,
            )
        )

        painter.drawRoundedRect(
            QRectF(
                panel_x,
                panel_y,
                panel_width,
                panel_height,
            ),
            8,
            8,
        )

        painter.setPen(
            QPen(
                QColor("#4edcff"),
                1,
            )
        )

        painter.drawRoundedRect(
            QRectF(
                panel_x,
                panel_y,
                panel_width,
                panel_height,
            ),
            8,
            8,
        )

        painter.setFont(
            QFont(
                "Cascadia Mono",
                9,
                QFont.Bold,
            )
        )

        painter.setPen(
            QColor("#75eaff")
        )

        painter.drawText(
            panel_x + 14,
            panel_y + 23,
            "SYSTEM MONITOR",
        )

        self._draw_status_row(
            painter,
            panel_x + 14,
            panel_y + 49,
            "EYES",
            eye_state,
            eye_state not in {
                "CLOSED",
                "DROWSY",
            },
        )

        self._draw_status_row(
            painter,
            panel_x + 14,
            panel_y + 73,
            "PHONE",
            phone_state,
            phone_state != "DETECTED",
        )

        self._draw_status_row(
            painter,
            panel_x + 14,
            panel_y + 97,
            "HANDS",
            hand_state,
            hand_state == "CLEAR",
        )

        self._draw_status_row(
            painter,
            panel_x + 14,
            panel_y + 121,
            "POSE",
            pose,
            pose == "CENTER",
        )

        self._draw_status_row(
            painter,
            panel_x + 14,
            panel_y + 145,
            "POSTURE",
            posture,
            posture != "POOR",
        )

        self._draw_status_row(
            painter,
            panel_x + 14,
            panel_y + 169,
            "USER",
            presence,
            presence == "PRESENT",
        )

        # --------------------------------------------------------------
        # EVENT INDICATOR
        # --------------------------------------------------------------

        event_text = str(
            hud_data.get(
                "STATUS",
                "FOCUS MODE ACTIVE",
            )
        )

        event_warning = bool(
            hud_data.get(
                "WARNING",
                False,
            )
        )

        event_height = 42
        event_panel_y = max(
            0,
            height - event_height - 12,
        )

        event_panel_width = min(
            460,
            max(
                300,
                width - 24,
            ),
        )

        event_color = (
            "#ff5c7a"
            if event_warning
            else "#4edcff"
        )

        painter.setPen(
            Qt.NoPen
        )

        painter.setBrush(
            QColor(
                4,
                10,
                18,
                215,
            )
        )

        painter.drawRoundedRect(
            QRectF(
                12,
                event_panel_y,
                event_panel_width,
                event_height,
            ),
            8,
            8,
        )

        painter.setPen(
            QPen(
                QColor(event_color),
                1,
            )
        )

        painter.drawRoundedRect(
            QRectF(
                12,
                event_panel_y,
                event_panel_width,
                event_height,
            ),
            8,
            8,
        )

        painter.setFont(
            QFont(
                "Segoe UI",
                11,
                QFont.Bold,
            )
        )

        painter.setPen(
            QColor(event_color)
        )

        painter.drawText(
            27,
            event_panel_y + 27,
            event_text[:52],
        )

        # --------------------------------------------------------------
        # TOP CENTER RETICLE
        # --------------------------------------------------------------

        center_x = width // 2
        reticle_y = 30

        painter.setPen(
            QPen(
                QColor(
                    90,
                    220,
                    255,
                    150,
                ),
                1,
            )
        )

        painter.drawLine(
            center_x - 18,
            reticle_y,
            center_x - 6,
            reticle_y,
        )

        painter.drawLine(
            center_x + 6,
            reticle_y,
            center_x + 18,
            reticle_y,
        )

        painter.drawLine(
            center_x,
            reticle_y - 8,
            center_x,
            reticle_y + 8,
        )

    # ==================================================================
    # STATUS ROW
    # ==================================================================

    def _draw_status_row(
        self,
        painter: QPainter,
        x: int,
        y: int,
        label: str,
        value: str,
        healthy: bool,
    ) -> None:

        painter.setFont(
            QFont(
                "Cascadia Mono",
                8,
            )
        )

        painter.setPen(
            QColor("#718898")
        )

        painter.drawText(
            x,
            y,
            f"{label:<8}",
        )

        painter.setPen(
            QColor(
                "#63f2b1"
                if healthy
                else "#ff5c7a"
            )
        )

        painter.drawText(
            x + 72,
            y,
            value,
        )

    # ==================================================================
    # SCAN OVERLAY
    # ==================================================================

    def _draw_scan_overlay(
        self,
        painter: QPainter,
        width: int,
        height: int,
    ) -> None:

        painter.setPen(
            QPen(
                QColor(
                    90,
                    220,
                    255,
                    22,
                ),
                1,
            )
        )

        grid_spacing = 48

        for x in range(
            0,
            width,
            grid_spacing,
        ):
            painter.drawLine(
                x,
                0,
                x,
                height,
            )

        for y in range(
            0,
            height,
            grid_spacing,
        ):
            painter.drawLine(
                0,
                y,
                width,
                y,
            )

        bracket = 24
        margin = 10

        painter.setPen(
            QPen(
                QColor(
                    90,
                    220,
                    255,
                    120,
                ),
                2,
            )
        )

        # Top-left
        painter.drawLine(
            margin,
            margin,
            margin + bracket,
            margin,
        )

        painter.drawLine(
            margin,
            margin,
            margin,
            margin + bracket,
        )

        # Top-right
        painter.drawLine(
            width - margin,
            margin,
            width - margin - bracket,
            margin,
        )

        painter.drawLine(
            width - margin,
            margin,
            width - margin,
            margin + bracket,
        )

        # Bottom-left
        painter.drawLine(
            margin,
            height - margin,
            margin + bracket,
            height - margin,
        )

        painter.drawLine(
            margin,
            height - margin,
            margin,
            height - margin - bracket,
        )

        # Bottom-right
        painter.drawLine(
            width - margin,
            height - margin,
            width - margin - bracket,
            height - margin,
        )

        painter.drawLine(
            width - margin,
            height - margin,
            width - margin,
            height - margin - bracket,
        )

    # ==================================================================
    # VISION MARKS
    # ==================================================================

    def _draw_vision_marks(
        self,
        painter: QPainter,
        width: int,
        height: int,
        hud_data: dict[str, Any],
    ) -> None:

        self._draw_eye_marks(
            painter,
            width,
            height,
            hud_data,
        )

        self._draw_mouth_marks(
            painter,
            width,
            height,
            hud_data,
        )

        self._draw_hand_marks(
            painter,
            width,
            height,
            hud_data,
        )

        self._draw_phone_box(
            painter,
            width,
            height,
            hud_data,
        )

        self._draw_pose_marks(
            painter,
            width,
            height,
            hud_data,
        )

        self._draw_posture_marks(
            painter,
            width,
            height,
            hud_data,
        )

    # ==================================================================
    # EYES
    # ==================================================================

    def _draw_eye_marks(
        self,
        painter: QPainter,
        width: int,
        height: int,
        hud_data: dict[str, Any],
    ) -> None:

        eye_points = (
            hud_data.get(
                "_eye_points"
            )
            or []
        )

        eye_closed = bool(
            hud_data.get(
                "_eye_closed",
                False,
            )
        )

        if not eye_points:
            return

        color = (
            QColor("#ff5c7a")
            if eye_closed
            else QColor("#ffe66d")
        )

        painter.setPen(
            QPen(
                color,
                2 if eye_closed else 1,
            )
        )

        painter.setBrush(
            Qt.NoBrush
        )

        left_eye = eye_points[:6]
        right_eye = eye_points[6:12]

        for eye in (
            left_eye,
            right_eye,
        ):
            if len(eye) >= 3:
                polygon = QPolygon(
                    [
                        self._point(
                            x,
                            y,
                            width,
                            height,
                        )
                        for x, y in eye
                    ]
                )

                painter.drawPolygon(
                    polygon
                )

        if eye_closed:
            avg_x = (
                sum(
                    p[0]
                    for p in eye_points
                )
                / len(eye_points)
            )

            avg_y = (
                sum(
                    p[1]
                    for p in eye_points
                )
                / len(eye_points)
            )

            self._draw_tag(
                painter,
                int(
                    avg_x * width
                ) - 48,
                int(
                    avg_y * height
                ) - 42,
                "EYES CLOSED",
                "#ff5c7a",
            )

    # ==================================================================
    # MOUTH / YAWN
    # ==================================================================

    def _draw_mouth_marks(
        self,
        painter: QPainter,
        width: int,
        height: int,
        hud_data: dict[str, Any],
    ) -> None:

        mouth_points = (
            hud_data.get(
                "_mouth_points"
            )
            or []
        )

        if len(mouth_points) < 2:
            return

        yawning = bool(
            hud_data.get(
                "_yawning",
                False,
            )
        )

        color = (
            QColor("#ff5c7a")
            if yawning
            else QColor("#d889ff")
        )

        painter.setPen(
            QPen(
                color,
                2 if yawning else 1,
            )
        )

        painter.setBrush(
            Qt.NoBrush
        )

        points: list[QPoint] = []

        for point in mouth_points:
            if len(point) < 2:
                continue

            try:
                x = float(point[0])
                y = float(point[1])
            except (
                TypeError,
                ValueError,
            ):
                continue

            points.append(
                self._point(
                    x,
                    y,
                    width,
                    height,
                )
            )

        if len(points) < 2:
            return

        painter.setBrush(
            QColor(
                216,
                137,
                255,
                80,
            )
        )

        for point in points:
            painter.drawEllipse(
                point.x() - 2,
                point.y() - 2,
                4,
                4,
            )

        painter.setBrush(
            Qt.NoBrush
        )

        for index in range(
            len(points) - 1
        ):
            painter.drawLine(
                points[index],
                points[index + 1],
            )

        if len(points) >= 3:
            painter.drawLine(
                points[-1],
                points[0],
            )

        if yawning:
            avg_x = (
                sum(
                    point.x()
                    for point in points
                )
                / len(points)
            )

            avg_y = (
                sum(
                    point.y()
                    for point in points
                )
                / len(points)
            )

            self._draw_tag(
                painter,
                int(avg_x) - 35,
                int(avg_y) + 12,
                "YAWN",
                "#ff5c7a",
            )

    # ==================================================================
    # HANDS
    # ==================================================================

    def _draw_hand_marks(
        self,
        painter: QPainter,
        width: int,
        height: int,
        hud_data: dict[str, Any],
    ) -> None:

        hand_groups = (
            hud_data.get(
                "_hand_points"
            )
            or []
        )

        if not hand_groups:
            return

        hand_near_camera = bool(
            hud_data.get(
                "_hand_near_camera",
                False,
            )
        )

        hand_color = (
            "#ff5c7a"
            if hand_near_camera
            else "#ffc857"
        )

        painter.setPen(
            QPen(
                QColor(hand_color),
                1,
            )
        )

        painter.setBrush(
            QColor(
                255,
                200,
                87,
                75,
            )
        )

        for hand in hand_groups:

            points: list[QPoint] = []

            for point in hand:

                if len(point) < 2:
                    continue

                try:
                    x = float(point[0])
                    y = float(point[1])
                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                px = int(
                    x * width
                )

                py = int(
                    y * height
                )

                points.append(
                    QPoint(
                        px,
                        py,
                    )
                )

                painter.drawEllipse(
                    px - 2,
                    py - 2,
                    4,
                    4,
                )

            if len(points) >= 2:

                painter.setPen(
                    QPen(
                        QColor(
                            255,
                            200,
                            87,
                            130,
                        ),
                        1,
                    )
                )

                for index in range(
                    len(points) - 1
                ):
                    painter.drawLine(
                        points[index],
                        points[index + 1],
                    )

            if (
                hand_near_camera
                and points
            ):

                avg_x = (
                    sum(
                        point.x()
                        for point in points
                    )
                    / len(points)
                )

                avg_y = (
                    sum(
                        point.y()
                        for point in points
                    )
                    / len(points)
                )

                self._draw_tag(
                    painter,
                    int(avg_x) - 45,
                    int(avg_y) - 35,
                    "HAND NEAR",
                    "#ff5c7a",
                )

    # ==================================================================
    # PHONE
    # ==================================================================

    def _draw_phone_box(
        self,
        painter: QPainter,
        width: int,
        height: int,
        hud_data: dict[str, Any],
    ) -> None:

        box = hud_data.get(
            "_phone_box"
        )

        if not box:
            return

        source_size = (
            hud_data.get(
                "_source_size"
            )
            or (
                width,
                height,
            )
        )

        source_w = max(
            1,
            int(
                source_size[0]
            ),
        )

        source_h = max(
            1,
            int(
                source_size[1]
            ),
        )

        scale_x = (
            width
            / source_w
        )

        scale_y = (
            height
            / source_h
        )

        try:
            x1, y1, x2, y2 = box

            left = int(
                x1 * scale_x
            )

            top = int(
                y1 * scale_y
            )

            box_width = int(
                (x2 - x1)
                * scale_x
            )

            box_height = int(
                (y2 - y1)
                * scale_y
            )

        except (
            TypeError,
            ValueError,
        ):
            return

        if (
            box_width <= 0
            or box_height <= 0
        ):
            return

        painter.setPen(
            QPen(
                QColor("#ff5c7a"),
                3,
            )
        )

        painter.setBrush(
            QColor(
                255,
                92,
                122,
                25,
            )
        )

        painter.drawRoundedRect(
            left,
            top,
            box_width,
            box_height,
            7,
            7,
        )

        accent = 12

        painter.setPen(
            QPen(
                QColor("#ff5c7a"),
                3,
            )
        )

        painter.drawLine(
            left,
            top,
            left + accent,
            top,
        )

        painter.drawLine(
            left,
            top,
            left,
            top + accent,
        )

        painter.drawLine(
            left + box_width,
            top,
            left + box_width - accent,
            top,
        )

        painter.drawLine(
            left + box_width,
            top,
            left + box_width,
            top + accent,
        )

        self._draw_tag(
            painter,
            left,
            max(
                18,
                top - 26,
            ),
            "PHONE DETECTED",
            "#ff5c7a",
        )

    # ==================================================================
    # HEAD POSE
    # ==================================================================

    def _draw_pose_marks(
        self,
        painter: QPainter,
        width: int,
        height: int,
        hud_data: dict[str, Any],
    ) -> None:

        pose = str(
            hud_data.get(
                "POSE",
                "",
            )
        ).upper()

        yaw = hud_data.get(
            "YAW"
        )

        pitch = hud_data.get(
            "PITCH"
        )

        if pose in {
            "",
            "UNKNOWN",
            "CENTER",
        }:
            return

        center_x = width // 2
        center_y = max(
            30,
            height - 96,
        )

        painter.setPen(
            QPen(
                QColor("#ffb84d"),
                2,
            )
        )

        painter.setFont(
            QFont(
                "Cascadia Mono",
                9,
                QFont.Bold,
            )
        )

        text = (
            f"HEAD // {pose}"
        )

        if isinstance(
            yaw,
            (int, float),
        ):
            text += (
                f"  Y:{float(yaw):+.0f}°"
            )

        if isinstance(
            pitch,
            (int, float),
        ):
            text += (
                f"  P:{float(pitch):+.0f}°"
            )

        painter.drawText(
            center_x - 90,
            center_y,
            text,
        )

    # ==================================================================
    # POSTURE
    # ==================================================================

    def _draw_posture_marks(
        self,
        painter: QPainter,
        width: int,
        height: int,
        hud_data: dict[str, Any],
    ) -> None:

        posture_points = (
            hud_data.get(
                "_posture_points"
            )
            or []
        )

        if len(posture_points) < 3:
            return

        posture = str(
            hud_data.get(
                "POSTURE",
                "",
            )
        ).upper()

        posture_color = (
            "#ff5c7a"
            if posture == "POOR"
            else "#6ef5be"
        )

        painter.setPen(
            QPen(
                QColor(posture_color),
                2,
            )
        )

        points: list[QPoint] = []

        for point in posture_points:

            if len(point) < 2:
                continue

            try:
                x = float(point[0])
                y = float(point[1])
            except (
                TypeError,
                ValueError,
            ):
                continue

            points.append(
                QPoint(
                    int(
                        x * width
                    ),
                    int(
                        y * height
                    ),
                )
            )

        if len(points) >= 2:

            for index in range(
                len(points) - 1
            ):
                painter.drawLine(
                    points[index],
                    points[index + 1],
                )

    # ==================================================================
    # TAG
    # ==================================================================

    def _draw_tag(
        self,
        painter: QPainter,
        x: int,
        y: int,
        text: str,
        color: str,
    ) -> None:

        font = QFont(
            "Cascadia Mono",
            9,
            QFont.Bold,
        )

        painter.setFont(
            font
        )

        metrics = (
            painter.fontMetrics()
        )

        text_width = (
            metrics.horizontalAdvance(
                text
            )
            + 16
        )

        text_height = (
            metrics.height()
            + 8
        )

        # Keep labels inside the camera.
        x = max(
            4,
            x,
        )

        y = max(
            4,
            y,
        )

        painter.setPen(
            QPen(
                QColor(color),
                1,
            )
        )

        painter.setBrush(
            QColor(
                4,
                10,
                18,
                220,
            )
        )

        painter.drawRoundedRect(
            QRectF(
                x,
                y,
                text_width,
                text_height,
            ),
            5,
            5,
        )

        painter.setPen(
            QColor(color)
        )

        painter.drawText(
            x + 8,
            y + metrics.ascent() + 4,
            text,
        )

    # ==================================================================
    # NORMALIZED POINT
    # ==================================================================

    def _point(
        self,
        x: float,
        y: float,
        width: int,
        height: int,
    ) -> QPoint:

        return QPoint(
            int(
                float(x) * width
            ),
            int(
                float(y) * height
            ),
        )

    # ==================================================================
    # SAFE FLOAT
    # ==================================================================

    @staticmethod
    def _safe_float(
        value: Any,
        default: float = 0.0,
    ) -> float:

        try:
            if isinstance(
                value,
                str,
            ):
                cleaned = (
                    value
                    .strip()
                    .replace(
                        "%",
                        "",
                    )
                )

                if not cleaned:
                    return default

                number = float(
                    cleaned
                )

                # "100%" -> 100, while FOCUS internally may expect
                # a percentage. Caller decides how to interpret it.
                return number

            return float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return default