# studyguard/ui/main_window.py

from __future__ import annotations

import logging
import time
from typing import Any

from PySide6.QtCore import QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from studyguard.audio.audio_manager import AudioManager
from studyguard.core.camera import CameraWorker, FramePacket
from studyguard.core.esp32_stream import ESP32StreamServer
from studyguard.core.focusforge_bridge import FocusForgeBridge
from studyguard.core.config import ConfigManager
from studyguard.core.event_engine import EventEngine
from studyguard.core.events import AppEvent, EventBus, EventType
from studyguard.core.focus_engine import FocusEngine
from studyguard.core.session import StudySession
from studyguard.core.state import AppState, StateManager
from studyguard.database.db import Database
from studyguard.database.repository import Repository
from studyguard.ui.analytics_page import AnalyticsPage
from studyguard.ui.calibration import CalibrationPage
from studyguard.ui.dashboard import Dashboard
from studyguard.ui.overlay import EventOverlay
from studyguard.ui.session_summary import SessionSummary
from studyguard.ui.settings import SettingsPage
from studyguard.ui.theme import DARK_QSS
from studyguard.vision.pipeline import VisionPipeline


logger = logging.getLogger(__name__)


def fmt(seconds: float) -> str:
    seconds = int(max(0, seconds))

    if seconds >= 3600:
        return (
            f"{seconds // 3600:02d}:"
            f"{seconds % 3600 // 60:02d}:"
            f"{seconds % 60:02d}"
        )

    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class CameraThread(QThread):
    frame_ready = Signal(object)
    camera_error = Signal(str)

    def __init__(self, worker: CameraWorker):
        super().__init__()

        self.worker = worker

        self.worker.on_frame = self.frame_ready.emit
        self.worker.on_error = self.camera_error.emit

    def run(self) -> None:
        self.worker.start()

    def stop(self) -> None:
        self.worker.stop()

        if self.isRunning():
            self.quit()
            self.wait(2000)


class MainWindow(QMainWindow):

    FOCUS_STREAK_MILESTONES = (
        300,
        900,
        1800,
        3600,
    )

    DISTRACTION_EVENTS = {
        EventType.PHONE_DETECTED,
        EventType.LOOKING_AWAY,
        EventType.DROWSINESS,
        EventType.USER_AWAY,
    }

    TRACKED_DETECTOR_EVENTS = {
        "phone": EventType.PHONE_DETECTED,
        "attention": EventType.LOOKING_AWAY,
        "eyes": EventType.DROWSINESS,
        "presence": EventType.USER_AWAY,
    }

    def __init__(
        self,
        config: ConfigManager,
        database: Database,
    ) -> None:
        super().__init__()

        self.config = config
        self.repo = Repository(database)

        self.state = StateManager()
        self.bus = EventBus()

        self.focus_engine = FocusEngine()

        self.event_engine = EventEngine(
            self.bus,
            config.config.detection,
        )

        self.audio = AudioManager(
            config.config.audio,
        )

        self.pipeline = VisionPipeline(
            config.config.detection,
        )

        self.session: StudySession | None = None

        self.last_vision_at = 0.0
        self.last_packet: FramePacket | None = None

        self.latest_results: dict[
            str,
            dict[str, Any],
        ] = {}

        self.user_was_away = False
        self.break_started_at: float | None = None
        self.pomodoro_next_break_at: float | None = None

        # --------------------------------------------------------------
        # WINDOW
        # --------------------------------------------------------------

        self.setWindowTitle(
            "StudyGuard AI",
        )

        self.resize(
            1320,
            900,
        )

        self.setStyleSheet(
            DARK_QSS,
        )

        # --------------------------------------------------------------
        # STACKED PAGES
        # --------------------------------------------------------------

        self.stack = QStackedWidget()

        self.dashboard = Dashboard()

        self.settings = SettingsPage(
            config,
            self.repo,
        )

        self.analytics = AnalyticsPage(
            self.repo,
        )

        self.summary = SessionSummary()

        self.calibration = CalibrationPage(
            config,
            self.repo,
        )

        self.stack.addWidget(
            self.dashboard,
        )

        self.stack.addWidget(
            self.analytics,
        )

        self.stack.addWidget(
            self.settings,
        )

        self.stack.addWidget(
            self.summary,
        )

        self.stack.addWidget(
            self.calibration,
        )

        # --------------------------------------------------------------
        # MAIN CENTRAL CONTAINER
        #
        # Navigation is kept OUTSIDE the layout that determines the
        # dashboard's available height. This prevents adding the HOME
        # button from pushing the dashboard controls below the screen.
        # --------------------------------------------------------------

        central = QWidget()

        central_layout = QVBoxLayout(
            central,
        )

        central_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        central_layout.setSpacing(
            0,
        )

        central_layout.addWidget(
            self.stack,
            1,
        )

        self.setCentralWidget(
            central,
        )

        # --------------------------------------------------------------
        # HOME BUTTON
        #
        # This is a floating navigation button. It does NOT participate
        # in the central layout, so it cannot reduce dashboard height.
        # --------------------------------------------------------------

        self.navigation_bar = QWidget(
            central,
        )

        self.navigation_bar.setObjectName(
            "NavigationBar",
        )

        self.navigation_bar.setAttribute(
            Qt.WA_StyledBackground,
            True,
        )

        self.navigation_bar.setFixedHeight(
            40,
        )

        self.navigation_layout = QHBoxLayout(
            self.navigation_bar,
        )

        self.navigation_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.navigation_layout.setSpacing(
            0,
        )

        self.home_button = QPushButton(
            "⌂  HOME",
            self.navigation_bar,
        )

        self.home_button.setObjectName(
            "HomeButton",
        )

        self.home_button.setMinimumHeight(
            38,
        )

        self.home_button.setMaximumHeight(
            38,
        )

        self.home_button.setCursor(
            Qt.PointingHandCursor,
        )

        self.home_button.clicked.connect(
            self.show_dashboard,
        )

        self.navigation_layout.addWidget(
            self.home_button,
        )

        self.navigation_layout.addStretch(
            1,
        )

        self.navigation_bar.hide()

        # --------------------------------------------------------------
        # EVENT OVERLAY
        # --------------------------------------------------------------

        self.overlay = EventOverlay(
            self.dashboard.camera,
        )

        # --------------------------------------------------------------
        # SYSTEM TRAY
        # --------------------------------------------------------------

        self.tray = QSystemTrayIcon(
            self,
        )

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

        # --------------------------------------------------------------
        # EVENT BUS
        # --------------------------------------------------------------

        self.bus.subscribe(
            self.handle_event,
        )

        # --------------------------------------------------------------
        # ESP32 TIMER + DISTRACTION SYNC (HTTP :8082)
        # Subscribe after handle_event so the session counters are updated
        # before the bridge forwards an event to the ESP32.
        # --------------------------------------------------------------

        self.esp32_bridge = FocusForgeBridge(
            esp32_url="http://192.168.29.204:8082/focus",
            event_bus=self.bus,
        )
        self.esp32_bridge.start()

        # --------------------------------------------------------------
        # UI CONNECTIONS
        # --------------------------------------------------------------

        self._connect_ui()

        # --------------------------------------------------------------
        # ESP32 LIVE STREAM SERVER (TCP :8080)
        # --------------------------------------------------------------

        self.esp32_stream = ESP32StreamServer(
            host="0.0.0.0",
            port=8080,
            width=320,
            height=240,
            fps=4,
            jpeg_quality=55,
        )
        self.esp32_stream.start()

        # --------------------------------------------------------------
        # CAMERA
        # --------------------------------------------------------------

        self._start_camera()

        # --------------------------------------------------------------
        # UI REFRESH TIMER
        # --------------------------------------------------------------

        self.ui_timer = QTimer(
            self,
        )

        self.ui_timer.timeout.connect(
            self.refresh_metrics,
        )

        self.ui_timer.start(
            250,
        )

        # --------------------------------------------------------------
        # INITIAL PAGE
        # --------------------------------------------------------------

        if not config.config.first_run_complete:

            self.stack.setCurrentWidget(
                self.calibration,
            )

        else:

            self.stack.setCurrentWidget(
                self.dashboard,
            )

            QTimer.singleShot(
                0,
                self._position_overlay,
            )

        self.state.set(
            AppState.READY,
        )

    # ==================================================================
    # WINDOW / NAVIGATION LAYOUT
    # ==================================================================

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

        self._position_navigation()

    def _position_navigation(self) -> None:
        """
        Position HOME as a floating button without consuming any
        vertical space from the stacked pages.
        """

        if not hasattr(
            self,
            "navigation_bar",
        ):
            return

        margin_left = 0
        margin_top = 0

        self.navigation_bar.setGeometry(
            margin_left,
            margin_top,
            self.navigation_bar.sizeHint().width(),
            40,
        )

        self.navigation_bar.raise_()

    # ==================================================================
    # GENERAL HELPERS
    # ==================================================================

    def _safe_float(
        self,
        value: Any,
    ) -> float:
        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return 0.0

    # ==================================================================
    # PAGE NAVIGATION
    # ==================================================================

    def show_dashboard(self) -> None:
        """
        Return to the main StudyGuard dashboard.
        """

        self.stack.setCurrentWidget(
            self.dashboard,
        )

        self.navigation_bar.hide()

        QTimer.singleShot(
            0,
            self._position_overlay,
        )

    def _on_page_changed(
        self,
        index: int,
    ) -> None:
        """
        Show HOME on every page except Dashboard.

        HOME is floating and therefore does not reduce the available
        height of the dashboard or any stacked page.
        """

        current = self.stack.widget(
            index,
        )

        is_dashboard = (
            current is self.dashboard
        )

        if is_dashboard:

            self.navigation_bar.hide()

            QTimer.singleShot(
                0,
                self._position_overlay,
            )

        else:

            self.navigation_bar.show()
            self._position_navigation()
            self.navigation_bar.raise_()

            if hasattr(
                self,
                "overlay",
            ):
                self.overlay.hide()

    # ==================================================================
    # UI CONNECTIONS
    # ==================================================================

    def _connect_ui(self) -> None:

        self.stack.currentChanged.connect(
            self._on_page_changed,
        )

        self.dashboard.start_button.clicked.connect(
            self.toggle_session,
        )

        self.dashboard.stop_button.clicked.connect(
            self.stop_session,
        )

        self.dashboard.settings_button.clicked.connect(
            lambda: self.stack.setCurrentWidget(
                self.settings,
            )
        )

        self.dashboard.analytics_button.clicked.connect(
            self.show_analytics,
        )

        self.dashboard.calibrate_button.clicked.connect(
            lambda: self.stack.setCurrentWidget(
                self.calibration,
            )
        )

        self.dashboard.camera.retry_requested.connect(
            self.retry_camera,
        )

        self.dashboard.camera.select_requested.connect(
            lambda: self.stack.setCurrentWidget(
                self.settings,
            )
        )

        self.dashboard.camera.timer_only_requested.connect(
            lambda: self.state.set(
                AppState.READY,
            )
        )

    # ==================================================================
    # CAMERA
    # ==================================================================

    def _start_camera(self) -> None:

        self.camera_worker = CameraWorker(
            self.config.config.camera,
        )

        self.camera_thread = CameraThread(
            self.camera_worker,
        )

        self.camera_thread.frame_ready.connect(
            self.on_frame,
        )

        self.camera_thread.camera_error.connect(
            self.on_camera_error,
        )

        self.camera_thread.start()

    def retry_camera(self) -> None:

        if hasattr(
            self,
            "camera_thread",
        ):
            self.camera_thread.stop()

        self.state.set(
            AppState.INITIALIZING,
        )

        self._start_camera()

    def on_camera_error(
        self,
        message: str,
    ) -> None:

        self.state.set(
            AppState.CAMERA_ERROR,
        )

        self.dashboard.camera.show_camera_error(
            message,
        )

        self.dashboard.set_online(
            False,
            self.focus_engine.score(
                self.session,
            ).score,
        )

    # ==================================================================
    # FRAME PROCESSING
    # ==================================================================

    def on_frame(
        self,
        packet: FramePacket,
    ) -> None:

        self.last_packet = packet

        # Forward the same real webcam frames to the ESP32. The stream
        # server performs JPEG encoding and socket I/O in its own thread.
        if hasattr(self, "esp32_stream") and not packet.mock:
            self.esp32_stream.submit_frame(packet.frame)

        now = packet.timestamp

        if (
            now - self.last_vision_at >= 0.2
            and not packet.mock
        ):

            self.last_vision_at = now

            try:

                results = self.pipeline.process(
                    packet.frame,
                    now,
                )

                for result in results:

                    metadata = dict(
                        result.metadata or {},
                    )

                    metadata.update(
                        {
                            "detected": result.detected,
                            "confidence": round(
                                result.confidence,
                                3,
                            ),
                        }
                    )

                    self.latest_results[
                        result.name
                    ] = metadata

                    if (
                        self.session is not None
                        and self.state.state
                        in {
                            AppState.STUDYING,
                            AppState.PAUSED,
                        }
                    ):

                        self._handle_detection(
                            result,
                            now,
                        )

            except Exception:

                logger.exception(
                    "Vision processing failed",
                )

        elif packet.mock:

            self.latest_results.update(
                {
                    "presence": {
                        "presence": "MOCK",
                        "present": False,
                        "face_visible": False,
                        "detected": False,
                    },
                    "eyes": {
                        "ear": 0.32,
                        "state": "OPEN",
                        "closed": False,
                    },
                    "attention": {
                        "pose": "CENTER",
                        "yaw": 0.0,
                        "pitch": 0.0,
                    },
                    "phone": {
                        "phone_confidence": 0.0,
                        "phone_box": None,
                        "available": False,
                    },
                    "posture": {
                        "posture": "UNKNOWN",
                    },
                    "hands": {
                        "hands": 0,
                        "hand_points": [],
                    },
                    "yawn": {
                        "mouth_points": [],
                        "mouth_open": False,
                        "yawning": False,
                    },
                }
            )

        try:

            hud = self._hud_data(
                packet,
            )

            self.dashboard.camera.update_frame(
                packet,
                hud,
            )

        except Exception:

            logger.exception(
                "Camera HUD update failed",
            )

        self._position_overlay()

    # ==================================================================
    # EVENT HANDLING
    # ==================================================================

    def _handle_detection(
        self,
        result,
        now: float,
    ) -> None:

        events = self.event_engine.process(
            result,
            now,
        )

        if result.name == "presence":

            presence = result.metadata.get(
                "presence",
            )

            present = (
                presence == "PRESENT"
            )

            if present and self.user_was_away:

                self.user_was_away = False

                self.bus.publish(
                    AppEvent(
                        EventType.USER_RETURNED,
                        timestamp=now,
                    )
                )

                if (
                    self.session
                    and self.session.is_paused
                ):

                    self.session.resume(
                        now,
                    )

                    self.state.set(
                        AppState.STUDYING,
                    )

        for event in events:

            if (
                event.event_type
                == EventType.USER_AWAY
            ):

                self.user_was_away = True

                if (
                    self.config.config.study.auto_pause
                    and self.session
                ):

                    self.session.pause(
                        now,
                    )

                    self.state.set(
                        AppState.PAUSED,
                    )

    def handle_event(
        self,
        event: AppEvent,
    ) -> None:

        if self.session is not None:

            self.session.add_event(
                event,
            )

        self.repo.add_event(
            self.session.id
            if self.session
            else None,
            event,
        )

        self.dashboard.timeline.add_event(
            event,
        )

        QTimer.singleShot(
            0,
            lambda ev=event: self._show_event_overlay(
                ev,
            ),
        )

        self.audio.play_for_event(
            event,
        )

        self.notify(
            event,
        )

    def _show_event_overlay(
        self,
        event: AppEvent,
    ) -> None:

        try:

            if self.stack.currentWidget() is not self.dashboard:
                return

            parent = self.dashboard.camera

            if self.overlay.parentWidget() is not parent:

                self.overlay.setParent(
                    parent,
                )

            self._position_overlay()

            hide_timer = getattr(
                self.overlay,
                "hide_timer",
                None,
            )

            if hide_timer is not None:
                hide_timer.stop()

            animation = getattr(
                self.overlay,
                "animation",
                None,
            )

            if animation is not None:
                animation.stop()

            self.overlay.setVisible(
                True,
            )

            self.overlay.raise_()

            self.overlay.show_event(
                event,
            )

            self.overlay.raise_()

        except Exception:

            logger.exception(
                "Failed to show event overlay: %s",
                getattr(
                    event.event_type,
                    "value",
                    event,
                ),
            )

    def notify(
        self,
        event: AppEvent,
    ) -> None:

        if not self.tray.isVisible():
            return

        if event.event_type in {
            EventType.PHONE_DETECTED,
            EventType.DROWSINESS,
            EventType.LOOKING_AWAY,
            EventType.BAD_POSTURE,
            EventType.YAWN,
            EventType.EXCESSIVE_BLINKING,
            EventType.USER_AWAY,
        }:

            title = (
                event.event_type.value
                .replace(
                    "_",
                    " ",
                )
                .title()
            )

            self.tray.showMessage(
                "StudyGuard AI",
                title,
                QSystemTrayIcon.Warning,
                2500,
            )

    # ==================================================================
    # SESSION
    # ==================================================================

    def toggle_session(self) -> None:

        if self.session is None:

            self.start_session()

        elif self.state.state == AppState.STUDYING:

            self.session.pause()

            self.state.set(
                AppState.PAUSED,
            )

            self.dashboard.start_button.setText(
                "RESUME",
            )

        elif self.state.state == AppState.PAUSED:

            self.session.resume()

            self.state.set(
                AppState.STUDYING,
            )

            self.dashboard.start_button.setText(
                "PAUSE",
            )

    def start_session(self) -> None:

        self.session = StudySession()
        self.break_started_at = None
        self.pomodoro_next_break_at = (
            max(1, int(self.config.config.study.study_minutes)) * 60
            if self.config.config.study.pomodoro_enabled
            else None
        )

        self.session.id = (
            self.repo.create_session(
                self.session,
            )
        )

        event = AppEvent(
            EventType.SESSION_START,
            timestamp=self.session.started_at,
        )

        self.handle_event(
            event,
        )

        self.state.set(
            AppState.STUDYING,
        )

        self.dashboard.start_button.setText(
            "PAUSE",
        )

        self.show_dashboard()

    def stop_session(self) -> None:

        if self.session is None:
            return

        self.session.end()

        score = self.focus_engine.score(
            self.session,
        )

        event = AppEvent(
            EventType.SESSION_END,
            timestamp=(
                self.session.ended_at
                or time.time()
            ),
        )

        self.handle_event(
            event,
        )

        self.repo.finish_session(
            self.session,
            score,
        )

        self.summary.load(
            self.session,
            score,
        )

        self.state.set(
            AppState.SESSION_COMPLETE,
        )

        self.stack.setCurrentWidget(
            self.summary,
        )

        self.session = None
        self.break_started_at = None
        self.pomodoro_next_break_at = None

        self.dashboard.start_button.setText(
            "START STUDY SESSION",
        )

    # ==================================================================
    # PAGES
    # ==================================================================

    def show_analytics(self) -> None:

        self.analytics.refresh()

        self.stack.setCurrentWidget(
            self.analytics,
        )

    # ==================================================================
    # METRICS
    # ==================================================================

    def refresh_metrics(self) -> None:

        score = self.focus_engine.score(
            self.session,
        )

        self.dashboard.focus.set_value(
            f"{score.score}%",
            score.explanation,
        )

        if self.session:

            elapsed = self.session.elapsed

            self._handle_pomodoro(
                elapsed,
            )

            focused = max(
                0.0,
                elapsed
                - self.session.distraction_seconds(),
            )

            self.dashboard.session.set_value(
                fmt(elapsed),
                f"Focused: {fmt(focused)}",
            )

            current_streak = (
                self.session.current_streak()
            )

            self.dashboard.streak.set_value(
                fmt(current_streak),
                (
                    "Best: "
                    f"{fmt(max(self.session.best_streak, current_streak))}"
                ),
            )

        # Publish the authoritative Windows timer/counter state.
        # The bridge throttles updates to one HTTP snapshot per second.
        if hasattr(self, "esp32_bridge"):
            study_cfg = self.config.config.study
            self.esp32_bridge.publish_state(
                session_state=self.state.state.value,
                session_elapsed_ms=(
                    int(self.session.elapsed * 1000)
                    if self.session is not None
                    else 0
                ),
                distraction_count=(
                    self.session.distraction_count
                    if self.session is not None
                    else 0
                ),
                pomodoro_enabled=bool(study_cfg.pomodoro_enabled),
                study_minutes=int(study_cfg.study_minutes),
                break_minutes=int(study_cfg.break_minutes),
                break_started_at=self.break_started_at,
                pomodoro_study_remaining_ms=(
                    max(
                        0,
                        int(
                            (
                                self.pomodoro_next_break_at
                                - self.session.elapsed
                            ) * 1000
                        ),
                    )
                    if (
                        self.session is not None
                        and self.pomodoro_next_break_at is not None
                    )
                    else int(max(1, int(study_cfg.study_minutes)) * 60 * 1000)
                ),
            )

        self.dashboard.set_online(
            self.state.state
            != AppState.CAMERA_ERROR,
            score.score,
        )

        self.dashboard.live_status.setText(
            self._live_status_text(),
        )

    # ==================================================================
    # POMODORO
    # ==================================================================

    def _handle_pomodoro(
        self,
        elapsed: float,
    ) -> None:

        if (
            not self.config.config.study.pomodoro_enabled
            or self.session is None
        ):
            return

        study_seconds = (
            self.config.config.study.study_minutes
            * 60
        )

        break_seconds = (
            self.config.config.study.break_minutes
            * 60
        )

        if self.pomodoro_next_break_at is None:
            self.pomodoro_next_break_at = study_seconds

        if (
            self.state.state
            == AppState.STUDYING
            and elapsed >= self.pomodoro_next_break_at
            and self.break_started_at is None
        ):

            self.break_started_at = time.time()

            self.state.set(
                AppState.BREAK,
            )

            self.session.pause()

            self.bus.publish(
                AppEvent(
                    EventType.BREAK_START,
                    timestamp=time.time(),
                )
            )

        elif (
            self.state.state
            == AppState.BREAK
            and self.break_started_at
            and time.time()
            - self.break_started_at
            >= break_seconds
        ):

            self.break_started_at = None
            self.pomodoro_next_break_at += study_seconds

            self.session.resume()

            self.state.set(
                AppState.STUDYING,
            )

            self.bus.publish(
                AppEvent(
                    EventType.BREAK_END,
                    timestamp=time.time(),
                )
            )

    # ==================================================================
    # LIVE STATUS
    # ==================================================================

    def _live_status_text(self) -> str:

        presence_data = self.latest_results.get(
            "presence",
            {},
        )

        presence = presence_data.get(
            "presence",
            "UNKNOWN",
        )

        attention = self.latest_results.get(
            "attention",
            {},
        ).get(
            "pose",
            "CENTER",
        )

        phone = self.latest_results.get(
            "phone",
            {},
        ).get(
            "phone_confidence",
            0.0,
        )

        posture = self.latest_results.get(
            "posture",
            {},
        ).get(
            "posture",
            "UNKNOWN",
        )

        eye = self.latest_results.get(
            "eyes",
            {},
        ).get(
            "state",
            "OPEN",
        )

        hands = self.latest_results.get(
            "hands",
            {},
        ).get(
            "hands",
            0,
        )

        latency = self.pipeline.last_latency_ms

        phone_threshold = float(
            getattr(
                self.config.config.detection,
                "phone_confidence",
                0.45,
            )
        )

        phone_state = (
            "DETECTED"
            if phone
            and phone >= phone_threshold
            else "CLEAR"
        )

        hand_state = (
            "ON CAMERA"
            if hands
            else "CLEAR"
        )

        eye_state = (
            "CLOSED"
            if eye in {
                "CLOSED",
                "DROWSY",
            }
            else str(eye)
        )

        return (
            f"Presence {presence}\n"
            f"Attention {attention}\n"
            f"Phone {phone_state}\n"
            f"Hand {hand_state}\n"
            f"Posture {posture}\n"
            f"Eyes {eye_state}\n"
            f"Latency {latency:.0f} ms\n"
            "Local processing active"
        )

    # ==================================================================
    # HUD DATA
    # ==================================================================

    def _hud_data(
        self,
        packet: FramePacket,
    ) -> dict[str, Any]:

        mode = str(
            self.config.config.ui.hud_mode
            or "standard"
        ).lower()

        score = self.focus_engine.score(
            self.session,
        ).score

        data: dict[str, Any] = {
            "FOCUS": float(score),
            "TIMER": fmt(
                self.session.elapsed
                if self.session
                else 0,
            ),
            "STATUS": self.state.state.value,
        }

        if mode != "minimal":

            presence_data = self.latest_results.get(
                "presence",
                {},
            )

            eyes_data = self.latest_results.get(
                "eyes",
                {},
            )

            attention_data = self.latest_results.get(
                "attention",
                {},
            )

            hands_data = self.latest_results.get(
                "hands",
                {},
            )

            phone_data = self.latest_results.get(
                "phone",
                {},
            )

            posture_data = self.latest_results.get(
                "posture",
                {},
            )

            yawn_data = self.latest_results.get(
                "yawn",
                {},
            )

            phone_conf = float(
                phone_data.get(
                    "phone_confidence",
                    0.0,
                )
                or 0.0
            )

            phone_threshold = float(
                getattr(
                    self.config.config.detection,
                    "phone_confidence",
                    0.45,
                )
            )

            phone_detected = (
                phone_conf >= phone_threshold
            )

            hand_count = int(
                hands_data.get(
                    "hands",
                    0,
                )
                or 0
            )

            eye_state = str(
                eyes_data.get(
                    "state",
                    "OPEN",
                )
            )

            presence = str(
                presence_data.get(
                    "presence",
                    "UNKNOWN",
                )
            )

            face_visible = bool(
                presence_data.get(
                    "face_visible",
                    presence == "PRESENT",
                )
            )

            data.update(
                {
                    "PRESENCE": presence,
                    "FACE_VISIBLE": face_visible,

                    "EAR": round(
                        float(
                            eyes_data.get(
                                "ear",
                                0.0,
                            )
                            or 0.0
                        ),
                        3,
                    ),

                    "EYES": (
                        "CLOSED"
                        if eye_state
                        in {
                            "CLOSED",
                            "DROWSY",
                        }
                        else eye_state
                    ),

                    "POSE": str(
                        attention_data.get(
                            "pose",
                            "CENTER",
                        )
                    ),

                    "PHONE": round(
                        phone_conf,
                        2,
                    ),

                    "PHONE_STATE": (
                        "DETECTED"
                        if phone_detected
                        else "CLEAR"
                    ),

                    "HAND": (
                        "ON CAMERA"
                        if hand_count
                        else "CLEAR"
                    ),

                    "POSTURE": str(
                        posture_data.get(
                            "posture",
                            "UNKNOWN",
                        )
                    ),

                    "CONFIDENCE": float(
                        attention_data.get(
                            "confidence",
                            0.0,
                        )
                    ),

                    "FPS": float(
                        getattr(
                            packet,
                            "fps",
                            0.0,
                        )
                    ),

                    "_eye_points": eyes_data.get(
                        "eye_points",
                        [],
                    ),

                    "_eye_closed": bool(
                        eyes_data.get(
                            "closed",
                            eye_state
                            in {
                                "CLOSED",
                                "DROWSY",
                            },
                        )
                    ),

                    "_hand_points": hands_data.get(
                        "hand_points",
                        [],
                    ),

                    "_hand_boxes": hands_data.get(
                        "hand_boxes",
                        [],
                    ),

                    "_phone_box": phone_data.get(
                        "phone_box",
                    ),

                    "_phone_confidence": phone_conf,

                    "_presence": presence,

                    "_face_visible": face_visible,

                    "YAW": self._safe_float(
                        attention_data.get(
                            "yaw",
                            0.0,
                        )
                    ),

                    "PITCH": self._safe_float(
                        attention_data.get(
                            "pitch",
                            0.0,
                        )
                    ),

                    "_face_points": attention_data.get(
                        "face_points",
                        [],
                    ),

                    "_posture_points": posture_data.get(
                        "landmarks",
                        [],
                    ),

                    "_mouth_points": yawn_data.get(
                        "mouth_points",
                        [],
                    ),

                    "_mouth_open": bool(
                        yawn_data.get(
                            "mouth_open",
                            False,
                        )
                    ),

                    "_yawn_detected": bool(
                        yawn_data.get(
                            "yawning",
                            False,
                        )
                    ),

                    "_source_size": (
                        (
                            packet.frame.shape[1],
                            packet.frame.shape[0],
                        )
                        if hasattr(
                            packet.frame,
                            "shape",
                        )
                        else None
                    ),
                }
            )

        if (
            mode == "developer"
            or self.config.config.ui.hud_mode
            == "developer"
        ):
            pass

        return data

    # ==================================================================
    # OVERLAY
    # ==================================================================

    def _position_overlay(self) -> None:

        if not hasattr(
            self,
            "overlay",
        ):
            return

        parent = self.dashboard.camera

        parent_width = max(
            1,
            parent.width(),
        )

        parent_height = max(
            1,
            parent.height(),
        )

        width = min(
            520,
            max(
                320,
                parent_width - 80,
            ),
        )

        height = 170

        x = max(
            0,
            (parent_width - width) // 2,
        )

        y = max(
            20,
            (parent_height - height) // 3,
        )

        self.overlay.setGeometry(
            x,
            y,
            width,
            height,
        )

    # ==================================================================
    # KEYBOARD
    # ==================================================================

    def keyPressEvent(
        self,
        event,
    ) -> None:

        if event.key() == Qt.Key_Space:

            self.toggle_session()

        elif event.key() == Qt.Key_Escape:

            self.stop_session()

        elif event.key() == Qt.Key_R:

            self.stack.setCurrentWidget(
                self.calibration,
            )

        elif event.key() == Qt.Key_M:

            self.config.config.audio.muted = (
                not self.config.config.audio.muted
            )

            self.config.save()

        elif event.key() == Qt.Key_H:

            modes = [
                "minimal",
                "standard",
                "developer",
            ]

            current = (
                self.config.config.ui.hud_mode
            )

            if current not in modes:
                current = "standard"

            next_index = (
                modes.index(current) + 1
            ) % len(modes)

            self.config.config.ui.hud_mode = (
                modes[next_index]
            )

            self.config.save()

        elif event.key() == Qt.Key_D:

            self.config.config.ui.developer_mode = (
                not self.config.config.ui.developer_mode
            )

            self.config.save()

        else:

            super().keyPressEvent(
                event,
            )

    # ==================================================================
    # SHUTDOWN
    # ==================================================================

    def closeEvent(
        self,
        event,
    ) -> None:

        if hasattr(
            self,
            "camera_thread",
        ):

            self.camera_thread.stop()

        if hasattr(self, "esp32_bridge"):
            self.esp32_bridge.stop()

        if hasattr(self, "esp32_stream"):
            self.esp32_stream.stop()

        if hasattr(
            self,
            "overlay",
        ):

            self.overlay.hide()

        if hasattr(
            self,
            "ui_timer",
        ):

            self.ui_timer.stop()

        super().closeEvent(
            event,
        )