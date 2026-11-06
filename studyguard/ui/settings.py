from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from studyguard.core.config import ConfigManager
from studyguard.database.repository import Repository


class SettingsPage(QWidget):
    def __init__(self, config: ConfigManager, repo: Repository):
        super().__init__()
        self.config = config
        self.repo = repo
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._camera_tab(), "Camera")
        tabs.addTab(self._detection_tab(), "Detection")
        tabs.addTab(self._audio_tab(), "Audio")
        tabs.addTab(self._study_tab(), "Study")
        tabs.addTab(self._privacy_tab(), "Privacy")
        layout.addWidget(tabs)

    def _camera_tab(self) -> QWidget:
        c = self.config.config.camera
        page = QWidget()
        form = QFormLayout(page)
        self.camera_index = QSpinBox()
        self.camera_index.setRange(0, 10)
        self.camera_index.setValue(c.index)
        self.camera_index.valueChanged.connect(lambda v: self._update("camera", "index", v))
        self.resolution = QComboBox()
        self.resolution.addItems(["640x480", "1280x720", "1920x1080"])
        self.resolution.setCurrentText(f"{c.width}x{c.height}")
        self.resolution.currentTextChanged.connect(self._set_resolution)
        self.mirror = QCheckBox("Mirror camera")
        self.mirror.setChecked(c.mirror)
        self.mirror.toggled.connect(lambda v: self._update("camera", "mirror", v))
        form.addRow("Camera index", self.camera_index)
        form.addRow("Resolution", self.resolution)
        form.addRow("", self.mirror)
        return page

    def _detection_tab(self) -> QWidget:
        d = self.config.config.detection
        page = QWidget()
        form = QFormLayout(page)
        for label, key, value, low, high, step in [
            ("Eye threshold", "eye_ear_threshold", d.eye_ear_threshold, 0.12, 0.35, 0.01),
            ("Drowsy duration", "drowsy_seconds", d.drowsy_seconds, 0.5, 5.0, 0.1),
            ("Yawn threshold", "yawn_mar_threshold", d.yawn_mar_threshold, 0.3, 1.2, 0.01),
            ("Looking-away seconds", "looking_away_seconds", d.looking_away_seconds, 0.5, 8.0, 0.1),
            ("Phone confidence", "phone_confidence", d.phone_confidence, 0.1, 0.9, 0.05),
            ("Posture warning seconds", "posture_warning_seconds", d.posture_warning_seconds, 1.0, 20.0, 0.5),
            ("Absence seconds", "absence_seconds", d.absence_seconds, 1.0, 10.0, 0.5),
        ]:
            spin = QDoubleSpinBox()
            spin.setRange(low, high)
            spin.setSingleStep(step)
            spin.setValue(value)
            spin.valueChanged.connect(lambda v, k=key: self._update("detection", k, v))
            form.addRow(label, spin)
        return page

    def _audio_tab(self) -> QWidget:
        a = self.config.config.audio
        page = QWidget()
        layout = QVBoxLayout(page)
        enabled = QCheckBox("Audio alerts enabled")
        enabled.setChecked(a.enabled)
        enabled.toggled.connect(lambda v: self._update("audio", "enabled", v))
        muted = QCheckBox("Mute")
        muted.setChecked(a.muted)
        muted.toggled.connect(lambda v: self._update("audio", "muted", v))
        layout.addWidget(enabled)
        layout.addWidget(muted)
        for event_name in ["DROWSINESS", "PHONE_DETECTED", "LOOKING_AWAY", "BAD_POSTURE", "YAWN", "BREAK_START", "BREAK_END", "SESSION_COMPLETE"]:
            row = QHBoxLayout()
            row.addWidget(QLabel(event_name.replace("_", " ").title()))
            button = QPushButton("Select sound")
            button.clicked.connect(lambda _=False, e=event_name: self._select_sound(e))
            row.addWidget(button)
            layout.addLayout(row)
        return page

    def _study_tab(self) -> QWidget:
        s = self.config.config.study
        page = QWidget()
        form = QFormLayout(page)
        pomodoro = QCheckBox("Pomodoro mode")
        pomodoro.setChecked(s.pomodoro_enabled)
        pomodoro.toggled.connect(lambda v: self._update("study", "pomodoro_enabled", v))
        study = QSpinBox()
        study.setRange(5, 120)
        study.setValue(s.study_minutes)
        study.valueChanged.connect(lambda v: self._update("study", "study_minutes", v))
        brk = QSpinBox()
        brk.setRange(1, 45)
        brk.setValue(s.break_minutes)
        brk.valueChanged.connect(lambda v: self._update("study", "break_minutes", v))
        auto = QCheckBox("Auto pause when away")
        auto.setChecked(s.auto_pause)
        auto.toggled.connect(lambda v: self._update("study", "auto_pause", v))
        form.addRow("", pomodoro)
        form.addRow("Study minutes", study)
        form.addRow("Break minutes", brk)
        form.addRow("", auto)
        return page

    def _privacy_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("LOCAL PROCESSING\nCamera analysis happens on this device. Webcam frames are not recorded or uploaded. Microphone is not used."))
        clear = QPushButton("CLEAR ALL STUDY DATA")
        clear.setObjectName("Danger")
        clear.clicked.connect(self._confirm_clear)
        export = QPushButton("EXPORT SESSION DATA CSV")
        export.clicked.connect(self._export)
        layout.addWidget(export)
        layout.addWidget(clear)
        layout.addStretch(1)
        return page

    def _set_resolution(self, text: str) -> None:
        width, height = [int(part) for part in text.split("x")]
        self.config.config.camera.width = width
        self.config.config.camera.height = height
        self.config.save()

    def _update(self, section: str, key: str, value: object) -> None:
        setattr(getattr(self.config.config, section), key, value)
        self.config.save()

    def _select_sound(self, event_name: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select alert sound", str(Path.home()), "Audio (*.wav *.mp3 *.ogg)")
        if path:
            self.config.config.audio.sounds[event_name] = path
            self.config.save()

    def _confirm_clear(self) -> None:
        if QMessageBox.question(self, "Clear data", "Clear all local StudyGuard session data?") == QMessageBox.Yes:
            self.repo.clear_all()

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export sessions", str(Path.home() / "studyguard_sessions.csv"), "CSV (*.csv)")
        if path:
            self.repo.export_sessions_csv(Path(path))
