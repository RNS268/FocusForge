# studyguard/core/config.py
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CameraSettings:
    index: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 30
    mirror: bool = True
    quality: str = "balanced"


@dataclass
class DetectionSettings:
    eye_ear_threshold: float = 0.21
    drowsy_seconds: float = 1.5
    blink_window_seconds: float = 0.5
    excessive_blinks_per_minute: int = 28

    yawn_mar_threshold: float = 0.62
    yawn_seconds: float = 1.0

    looking_away_seconds: float = 2.0
    head_yaw_threshold: float = 22.0
    head_pitch_threshold: float = 18.0

    phone_confidence: float = 0.45
    phone_persistence_frames: int = 4

    posture_warning_seconds: float = 6.0
    absence_seconds: float = 3.0

    # Additional persistence / stability controls.
    eye_persistence_frames: int = 3
    hand_persistence_frames: int = 3
    yawn_persistence_frames: int = 3
    attention_persistence_frames: int = 3
    posture_persistence_frames: int = 3


@dataclass
class AudioSettings:
    enabled: bool = True
    muted: bool = False
    master_volume: float = 0.7

    cooldowns: dict[str, float] = field(
        default_factory=lambda: {
            "DROWSINESS": 15.0,
            "PHONE_DETECTED": 10.0,
            "LOOKING_AWAY": 15.0,
            "BAD_POSTURE": 20.0,
            "YAWN": 20.0,
            "EXCESSIVE_BLINKING": 20.0,
            "USER_AWAY": 15.0,
            "USER_RETURNED": 5.0,
            "FOCUS_RESTORED": 5.0,
            "FOCUS_STREAK": 30.0,
            "BREAK_START": 30.0,
            "BREAK_END": 30.0,
        }
    )

    sounds: dict[str, str] = field(default_factory=dict)


@dataclass
class StudySettings:
    pomodoro_enabled: bool = False
    study_minutes: int = 25
    break_minutes: int = 5
    auto_pause: bool = True

    # Optional automatic focus-cycle behaviour.
    auto_start_break: bool = False
    auto_resume_after_break: bool = False


@dataclass
class UiSettings:
    theme: str = "dark"
    hud_mode: str = "standard"
    animation_intensity: float = 0.75
    developer_mode: bool = False

    # Camera HUD preferences.
    show_face_landmarks: bool = True
    show_eye_tracking: bool = True
    show_hand_tracking: bool = True
    show_phone_box: bool = True
    show_status_text: bool = True
    show_fps: bool = True
    show_detection_confidence: bool = True


@dataclass
class AppConfig:
    camera: CameraSettings = field(default_factory=CameraSettings)
    detection: DetectionSettings = field(default_factory=DetectionSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    study: StudySettings = field(default_factory=StudySettings)
    ui: UiSettings = field(default_factory=UiSettings)

    first_run_complete: bool = False
    calibration: dict[str, Any] = field(default_factory=dict)


class ConfigManager:
    def __init__(self, path: Path):
        self.path = path

        self.user_data_dir = Path.home() / "StudyGuardAI"
        try:
            self.user_data_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            self.user_data_dir = Path.cwd() / "StudyGuardAI"
            self.user_data_dir.mkdir(parents=True, exist_ok=True)

        self.config = AppConfig()
        self.load()

    def load(self) -> AppConfig:
        if not self.path.exists():
            self.save()
            return self.config

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.config = AppConfig()
            self.save()
            return self.config

        self.config = AppConfig(
            camera=self._build_section(
                CameraSettings,
                data.get("camera", {}),
            ),
            detection=self._build_section(
                DetectionSettings,
                data.get("detection", {}),
            ),
            audio=self._build_section(
                AudioSettings,
                data.get("audio", {}),
            ),
            study=self._build_section(
                StudySettings,
                data.get("study", {}),
            ),
            ui=self._build_section(
                UiSettings,
                data.get("ui", {}),
            ),
            first_run_complete=bool(
                data.get("first_run_complete", False)
            ),
            calibration=data.get("calibration", {})
            if isinstance(data.get("calibration", {}), dict)
            else {},
        )

        return self.config

    @staticmethod
    def _build_section(cls: Any, values: Any) -> Any:
        if not isinstance(values, dict):
            values = {}

        defaults = asdict(cls())

        # Ignore obsolete/unknown configuration keys so an older config
        # continues to work after new settings are introduced.
        supported = {
            key: value
            for key, value in values.items()
            if key in defaults
        }

        return cls(**supported)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.path.write_text(
            json.dumps(
                asdict(self.config),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def update(self, **sections: Any) -> None:
        for name, values in sections.items():
            if not hasattr(self.config, name):
                continue

            target = getattr(self.config, name)

            if not isinstance(values, dict):
                continue

            for key, value in values.items():
                if hasattr(target, key):
                    setattr(target, key, value)

        self.save()