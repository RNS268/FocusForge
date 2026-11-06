# studyguard/ui/overlay.py

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from studyguard.core.events import AppEvent


OVERLAY_COPY = {
    "DROWSINESS": (
        "DROWSINESS",
        "EYES CLOSED TOO LONG",
        "#ff4d6d",
    ),
    "EXCESSIVE_BLINKING": (
        "EYE STRAIN",
        "EXCESSIVE BLINKING DETECTED",
        "#ffc857",
    ),
    "PHONE_DETECTED": (
        "DISTRACTION",
        "PHONE DETECTED  //  PUT IT DOWN",
        "#ff4d6d",
    ),
    "LOOKING_AWAY": (
        "ATTENTION LOST",
        "RETURN TO STUDY",
        "#ffc857",
    ),
    "BAD_POSTURE": (
        "POSTURE ALERT",
        "STRAIGHTEN YOUR BACK",
        "#ffc857",
    ),
    "YAWN": (
        "FATIGUE DETECTED",
        "CONSIDER A SHORT BREAK",
        "#8ee8ff",
    ),
    "USER_AWAY": (
        "USER NOT DETECTED",
        "SESSION PAUSED",
        "#ffc857",
    ),
    "USER_RETURNED": (
        "USER DETECTED",
        "SESSION RESUMED",
        "#6dff9f",
    ),
    "FOCUS_RESTORED": (
        "FOCUS RESTORED",
        "STAY LOCKED IN",
        "#6dff9f",
    ),
    "FOCUS_STREAK": (
        "FOCUS STREAK",
        "UNINTERRUPTED MOMENTUM",
        "#6dff9f",
    ),
}


class EventOverlay(QWidget):
    """
    In-app event popup.

    Animation lifecycle is deliberately kept simple:

        show_event()
            -> stop old animations
            -> show widget
            -> fade in
            -> timer
            -> fade out
            -> hide

    The fade-out animation's finished signal is connected exactly once
    during initialization. It is NEVER dynamically connected/disconnected.
    """

    DISPLAY_MS = 2600
    FADE_IN_MS = 180
    FADE_OUT_MS = 220

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._accent = "#8ee8ff"
        self._is_showing = False

        # ------------------------------------------------------------------
        # Widget configuration
        # ------------------------------------------------------------------

        self.setObjectName("StudyGuardEventOverlay")

        self.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )

        self.setAttribute(
            Qt.WA_TranslucentBackground,
            True,
        )

        self.setAttribute(
            Qt.WA_NoSystemBackground,
            True,
        )

        self.setFocusPolicy(Qt.NoFocus)

        self.setMinimumSize(
            420,
            180,
        )

        self.setMaximumWidth(
            620,
        )

        self.setWindowOpacity(0.0)

        # ------------------------------------------------------------------
        # Layout
        # ------------------------------------------------------------------

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            32,
            26,
            32,
            26,
        )

        layout.setSpacing(8)

        # ------------------------------------------------------------------
        # Status
        # ------------------------------------------------------------------

        self.status = QLabel(
            "●  STUDYGUARD AI  //  EVENT"
        )

        self.status.setAlignment(
            Qt.AlignCenter
        )

        self.status.setStyleSheet(
            """
            QLabel {
                background: transparent;
                color: #8ee8ff;
                font-family: "Cascadia Mono", "Consolas", monospace;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 2px;
            }
            """
        )

        # ------------------------------------------------------------------
        # Title
        # ------------------------------------------------------------------

        self.title = QLabel("")

        self.title.setAlignment(
            Qt.AlignCenter
        )

        self.title.setWordWrap(True)

        self.title.setStyleSheet(
            """
            QLabel {
                background: transparent;
                color: #ffffff;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 28px;
                font-weight: 900;
                letter-spacing: 1px;
            }
            """
        )

        # ------------------------------------------------------------------
        # Subtitle
        # ------------------------------------------------------------------

        self.subtitle = QLabel("")

        self.subtitle.setAlignment(
            Qt.AlignCenter
        )

        self.subtitle.setWordWrap(True)

        self.subtitle.setStyleSheet(
            """
            QLabel {
                background: transparent;
                color: #c8f7ff;
                font-family: "Cascadia Mono", "Consolas", monospace;
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }
            """
        )

        # ------------------------------------------------------------------
        # Footer
        # ------------------------------------------------------------------

        self.footer = QLabel(
            "MONITORING  //  TAKE ACTION"
        )

        self.footer.setAlignment(
            Qt.AlignCenter
        )

        self.footer.setStyleSheet(
            """
            QLabel {
                background: transparent;
                color: #78909c;
                font-family: "Cascadia Mono", "Consolas", monospace;
                font-size: 9px;
                font-weight: 600;
                letter-spacing: 1.5px;
                padding-top: 8px;
            }
            """
        )

        layout.addWidget(self.status)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.footer)

        # ------------------------------------------------------------------
        # Fade-in animation
        #
        # Separate animation object.
        # ------------------------------------------------------------------

        self.fade_in_animation = QPropertyAnimation(
            self,
            b"windowOpacity",
            self,
        )

        self.fade_in_animation.setDuration(
            self.FADE_IN_MS
        )

        self.fade_in_animation.setEasingCurve(
            QEasingCurve.OutCubic
        )

        # ------------------------------------------------------------------
        # Fade-out animation
        #
        # IMPORTANT:
        # finished() is connected ONCE.
        #
        # Never disconnect/reconnect this signal in show_event() or
        # fade_out().
        # ------------------------------------------------------------------

        self.fade_out_animation = QPropertyAnimation(
            self,
            b"windowOpacity",
            self,
        )

        self.fade_out_animation.setDuration(
            self.FADE_OUT_MS
        )

        self.fade_out_animation.setEasingCurve(
            QEasingCurve.InCubic
        )

        self.fade_out_animation.finished.connect(
            self._hide_after_animation
        )

        # ------------------------------------------------------------------
        # Hide timer
        # ------------------------------------------------------------------

        self.hide_timer = QTimer(self)

        self.hide_timer.setSingleShot(True)

        self.hide_timer.timeout.connect(
            self.fade_out
        )

        # ------------------------------------------------------------------
        # Start hidden
        # ------------------------------------------------------------------

        self.hide()

    # ======================================================================
    # GEOMETRY
    # ======================================================================

    def _position_over_parent(self) -> None:
        """
        Centre the popup over the parent widget.
        """

        parent = self.parentWidget()

        if parent is None:
            return

        parent_rect = parent.rect()

        if parent_rect.width() <= 0:
            return

        if parent_rect.height() <= 0:
            return

        width = min(
            560,
            max(
                420,
                parent_rect.width() - 80,
            ),
        )

        height = min(
            205,
            max(
                180,
                parent_rect.height() - 80,
            ),
        )

        self.setFixedSize(
            int(width),
            int(height),
        )

        x = (
            parent_rect.width()
            - self.width()
        ) // 2

        y = (
            parent_rect.height()
            - self.height()
        ) // 2

        # Slightly above exact centre.
        y -= 20

        x = max(
            20,
            min(
                x,
                parent_rect.width()
                - self.width()
                - 20,
            ),
        )

        y = max(
            20,
            min(
                y,
                parent_rect.height()
                - self.height()
                - 20,
            ),
        )

        self.move(
            int(x),
            int(y),
        )

    # ======================================================================
    # PAINT
    # ======================================================================

    def paintEvent(
        self,
        event,
    ) -> None:
        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.Antialiasing,
            True,
        )

        rect = self.rect().adjusted(
            1,
            1,
            -1,
            -1,
        )

        # Main translucent panel.
        painter.setBrush(
            QColor(
                5,
                11,
                17,
                245,
            )
        )

        painter.setPen(
            QPen(
                QColor(self._accent),
                1.5,
            )
        )

        painter.drawRoundedRect(
            rect,
            14,
            14,
        )

        # ------------------------------------------------------------------
        # Futuristic corner brackets
        # ------------------------------------------------------------------

        painter.setPen(
            QPen(
                QColor(self._accent),
                2,
            )
        )

        length = 22
        margin = 10

        # Top-left
        painter.drawLine(
            rect.left() + margin,
            rect.top() + margin,
            rect.left() + margin + length,
            rect.top() + margin,
        )

        painter.drawLine(
            rect.left() + margin,
            rect.top() + margin,
            rect.left() + margin,
            rect.top() + margin + length,
        )

        # Top-right
        painter.drawLine(
            rect.right() - margin - length,
            rect.top() + margin,
            rect.right() - margin,
            rect.top() + margin,
        )

        painter.drawLine(
            rect.right() - margin,
            rect.top() + margin,
            rect.right() - margin,
            rect.top() + margin + length,
        )

        # Bottom-left
        painter.drawLine(
            rect.left() + margin,
            rect.bottom() - margin,
            rect.left() + margin + length,
            rect.bottom() - margin,
        )

        painter.drawLine(
            rect.left() + margin,
            rect.bottom() - margin - length,
            rect.left() + margin,
            rect.bottom() - margin,
        )

        # Bottom-right
        painter.drawLine(
            rect.right() - margin - length,
            rect.bottom() - margin,
            rect.right() - margin,
            rect.bottom() - margin,
        )

        painter.drawLine(
            rect.right() - margin,
            rect.bottom() - margin - length,
            rect.right() - margin,
            rect.bottom() - margin,
        )

        # ------------------------------------------------------------------
        # Divider
        # ------------------------------------------------------------------

        divider_y = rect.bottom() - 42

        painter.setPen(
            QPen(
                QColor(self._accent),
                1,
            )
        )

        painter.drawLine(
            rect.left() + 42,
            divider_y,
            rect.right() - 42,
            divider_y,
        )

        painter.end()

        super().paintEvent(event)

    # ======================================================================
    # SHOW EVENT
    # ======================================================================

    def show_event(
        self,
        event: AppEvent,
    ) -> None:
        """
        Display an event popup.

        This method is safe to call repeatedly during the same session.
        """

        event_type = getattr(
            getattr(
                event,
                "event_type",
                None,
            ),
            "value",
            str(
                getattr(
                    event,
                    "event_type",
                    "EVENT",
                )
            ),
        )

        title, subtitle, color = OVERLAY_COPY.get(
            event_type,
            (
                event_type,
                "",
                "#8ee8ff",
            ),
        )

        self._accent = color

        # ------------------------------------------------------------------
        # Update content FIRST.
        # ------------------------------------------------------------------

        self.status.setText(
            f"●  STUDYGUARD AI  //  {event_type}"
        )

        self.title.setText(title)

        self.subtitle.setText(subtitle)

        duration = float(
            getattr(
                event,
                "duration",
                0.0,
            )
            or 0.0
        )

        confidence = float(
            getattr(
                event,
                "confidence",
                0.0,
            )
            or 0.0
        )

        if confidence > 0:
            self.footer.setText(
                f"CONFIDENCE {confidence:.0%}"
                f"   //   DURATION {duration:.1f}s"
            )
        else:
            self.footer.setText(
                "MONITORING  //  TAKE ACTION"
            )

        self._update_label_styles(color)

        # ------------------------------------------------------------------
        # CRITICAL:
        #
        # Stop BOTH animations.
        #
        # A previous fade-out must never be allowed to finish after this
        # event has started displaying.
        # ------------------------------------------------------------------

        self.fade_in_animation.stop()
        self.fade_out_animation.stop()

        self.hide_timer.stop()

        # ------------------------------------------------------------------
        # Reposition every time.
        # ------------------------------------------------------------------

        self._position_over_parent()

        # ------------------------------------------------------------------
        # Make popup visible immediately.
        #
        # Do NOT rely on animation to make the widget visible.
        # ------------------------------------------------------------------

        self.setWindowOpacity(0.0)

        self.show()
        self.raise_()

        self._is_showing = True

        self.update()
        self.repaint()

        # ------------------------------------------------------------------
        # Fade in.
        # ------------------------------------------------------------------

        self.fade_in_animation.setStartValue(
            0.0
        )

        self.fade_in_animation.setEndValue(
            1.0
        )

        self.fade_in_animation.start()

        # ------------------------------------------------------------------
        # Start visibility timer.
        #
        # Every event gets a fresh timer.
        # ------------------------------------------------------------------

        self.hide_timer.start(
            self.DISPLAY_MS
        )

    # ======================================================================
    # FADE OUT
    # ======================================================================

    def fade_out(self) -> None:
        """
        Start the fade-out.

        No signal connections are changed here.
        """

        if not self.isVisible():
            self._is_showing = False
            return

        self.hide_timer.stop()

        # Stop fade-in if the popup is still entering.
        self.fade_in_animation.stop()

        # Stop any previous fade-out.
        self.fade_out_animation.stop()

        current_opacity = self.windowOpacity()

        # Already invisible.
        if current_opacity <= 0.01:
            self._hide_after_animation()
            return

        self.fade_out_animation.setStartValue(
            current_opacity
        )

        self.fade_out_animation.setEndValue(
            0.0
        )

        self.fade_out_animation.start()

    # ======================================================================
    # FADE OUT FINISHED
    # ======================================================================

    def _hide_after_animation(self) -> None:
        """
        Final cleanup after fade-out.

        This is connected ONCE in __init__ and is never dynamically
        connected/disconnected.
        """

        self.fade_out_animation.stop()

        self.fade_in_animation.stop()

        self.hide_timer.stop()

        self.setWindowOpacity(
            0.0
        )

        self.hide()

        self._is_showing = False

        self.update()

    # ======================================================================
    # RESIZE
    # ======================================================================

    def resizeEvent(
        self,
        event,
    ) -> None:
        super().resizeEvent(
            event
        )

        if self.isVisible():
            QTimer.singleShot(
                0,
                self._position_over_parent,
            )

    # ======================================================================
    # LABEL STYLES
    # ======================================================================

    def _update_label_styles(
        self,
        color: str,
    ) -> None:
        self.status.setStyleSheet(
            f"""
            QLabel {{
                background: transparent;
                color: {color};
                font-family: "Cascadia Mono", "Consolas", monospace;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 2px;
            }}
            """
        )

        self.title.setStyleSheet(
            """
            QLabel {
                background: transparent;
                color: #ffffff;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 28px;
                font-weight: 900;
                letter-spacing: 1px;
            }
            """
        )

        self.subtitle.setStyleSheet(
            """
            QLabel {
                background: transparent;
                color: #c8f7ff;
                font-family: "Cascadia Mono", "Consolas", monospace;
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }
            """
        )

        self.footer.setStyleSheet(
            f"""
            QLabel {{
                background: transparent;
                color: {color};
                font-family: "Cascadia Mono", "Consolas", monospace;
                font-size: 9px;
                font-weight: 600;
                letter-spacing: 1.5px;
                padding-top: 8px;
            }}
            """
        )