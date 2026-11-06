# studyguard/audio/audio_manager.py

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from studyguard.core.alert_engine import AlertEngine
from studyguard.core.config import AudioSettings
from studyguard.core.events import AppEvent


logger = logging.getLogger(__name__)


class AudioManager:
    """
    Centralized audio manager for StudyGuard.

    Supports:
    - Separate custom MP3 sound for each event
    - Windows / Qt Multimedia playback
    - Fallback Windows beeps
    - AlertEngine cooldown handling
    - Master volume
    - Mute / enable controls
    - Non-blocking playback
    - Safe cleanup
    """

    def __init__(self, settings: AudioSettings):
        self.settings = settings
        self.alerts = AlertEngine(settings)

        # event_name -> (QMediaPlayer, QAudioOutput)
        self._players: dict[str, tuple[Any, Any]] = {}

        self._lock = threading.Lock()

        self._initialized = False
        self._qt_available = False

        self._sound_directory = (
            Path(__file__).resolve().parents[2]
            / "assets"
            / "sounds"
        )

        self._initialize_multimedia()

    # ==================================================================
    # INITIALIZATION
    # ==================================================================

    def _initialize_multimedia(self) -> None:
        """
        Initialize Qt Multimedia.

        QMediaPlayer is intentionally used instead of QSoundEffect
        because the StudyGuard custom sounds are MP3 files.
        """
        try:
            from PySide6.QtMultimedia import (
                QAudioOutput,
                QMediaPlayer,
            )

            # Import check only.
            _ = QMediaPlayer
            _ = QAudioOutput

            self._qt_available = True
            self._initialized = True

            logger.info(
                "Qt Multimedia initialized successfully"
            )

            logger.info(
                "StudyGuard sound directory: %s",
                self._sound_directory,
            )

        except Exception as exc:
            self._qt_available = False
            self._initialized = False

            logger.warning(
                "Qt Multimedia unavailable: %s",
                exc,
            )

    # ==================================================================
    # EVENT PLAYBACK
    # ==================================================================

    def play_for_event(
        self,
        event: AppEvent,
    ) -> None:
        """
        Play the configured/custom sound for an application event.

        AlertEngine controls event cooldowns.
        """

        if not self._audio_enabled():
            return

        event_name = event.event_type.value

        if not self.alerts.can_alert(
            event_name,
            event.timestamp,
        ):
            return

        path = self._sound_for_event(
            event_name
        )

        played = False

        if path is not None:
            played = self._play_file(
                event_name,
                path,
            )

        if not played:
            played = self._beep(
                event_name
            )

        if played:
            self.alerts.mark_alerted(event)

    # ==================================================================
    # DIRECT SOUND PLAYBACK
    # ==================================================================

    def play_sound(
        self,
        path: str | Path,
        event_name: str = "CUSTOM",
    ) -> bool:
        """
        Play an arbitrary sound file.
        """

        if not self._audio_enabled():
            return False

        return self._play_file(
            event_name,
            Path(path),
        )

    # ==================================================================
    # PREVIEW
    # ==================================================================

    def preview_event(
        self,
        event_name: str,
    ) -> bool:
        """
        Preview an event sound without affecting AlertEngine cooldowns.
        """

        if not self._audio_enabled():
            return False

        path = self._sound_for_event(
            event_name
        )

        if path is not None:
            return self._play_file(
                f"preview:{event_name}",
                path,
            )

        return self._beep(
            event_name
        )

    # ==================================================================
    # SOUND MAPPING
    # ==================================================================

    def _sound_for_event(
        self,
        event_name: str,
    ) -> Path | None:
        """
        Return the sound file for a specific StudyGuard event.

        Files:

        assets/sounds/
            start.mp3
            drowsiness.mp3
            phone.mp3
            away.mp3
            bad_posture.mp3
            yawn.mp3
            complete.mp3
        """

        # --------------------------------------------------------------
        # Default StudyGuard sound mapping
        # --------------------------------------------------------------

        default_sounds: dict[str, str] = {
            "SESSION_START": "start.mp3",

            "DROWSINESS": "drowsiness.mp3",

            "PHONE_DETECTED": "phone.mp3",

            "LOOKING_AWAY": "away.mp3",

            "BAD_POSTURE": "bad_posture.mp3",

            "YAWN": "yawn.mp3",

            "SESSION_END": "complete.mp3",
        }

        # --------------------------------------------------------------
        # First allow an explicitly configured sound from settings.
        # --------------------------------------------------------------

        try:
            sounds = self.settings.sounds

            if sounds:
                configured = sounds.get(
                    event_name,
                    "",
                )

                if configured:
                    configured_path = Path(
                        str(configured).strip()
                    )

                    if configured_path.exists():
                        return configured_path

                    logger.warning(
                        "Configured sound does not exist: %s",
                        configured_path,
                    )

        except (
            AttributeError,
            TypeError,
        ):
            pass

        # --------------------------------------------------------------
        # Fall back to StudyGuard's built-in custom mapping.
        # --------------------------------------------------------------

        filename = default_sounds.get(
            event_name
        )

        if not filename:
            return None

        path = (
            self._sound_directory
            / filename
        )

        if not path.exists():
            logger.warning(
                "StudyGuard custom sound missing: %s",
                path,
            )
            return None

        if not path.is_file():
            logger.warning(
                "StudyGuard custom sound is not a file: %s",
                path,
            )
            return None

        return path

    # ==================================================================
    # FILE PLAYBACK
    # ==================================================================

    def _play_file(
        self,
        event_name: str,
        path: Path,
    ) -> bool:
        """
        Play an MP3/WAV/etc. local audio file using QMediaPlayer.

        QMediaPlayer is used because the StudyGuard custom sounds
        are MP3 files.
        """

        if not path.exists():
            logger.warning(
                "Custom sound missing: %s",
                path,
            )
            return False

        if not path.is_file():
            logger.warning(
                "Custom sound is not a file: %s",
                path,
            )
            return False

        if not self._qt_available:
            logger.warning(
                "Qt Multimedia unavailable; cannot play %s",
                path,
            )
            return False

        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import (
                QAudioOutput,
                QMediaPlayer,
            )

            # ----------------------------------------------------------
            # Stop an existing sound for this event.
            # ----------------------------------------------------------

            self.stop_event_sound(
                event_name
            )

            # ----------------------------------------------------------
            # Create player + audio output.
            # ----------------------------------------------------------

            player = QMediaPlayer()
            audio_output = QAudioOutput()

            volume = max(
                0.0,
                min(
                    1.0,
                    float(
                        getattr(
                            self.settings,
                            "master_volume",
                            1.0,
                        )
                    ),
                ),
            )

            audio_output.setVolume(
                volume
            )

            player.setAudioOutput(
                audio_output
            )

            player.setSource(
                QUrl.fromLocalFile(
                    str(
                        path.resolve()
                    )
                )
            )

            # ----------------------------------------------------------
            # Keep player alive while playing.
            # ----------------------------------------------------------

            with self._lock:
                self._players[event_name] = (
                    player,
                    audio_output,
                )

            # ----------------------------------------------------------
            # Cleanup when playback finishes.
            # ----------------------------------------------------------

            def cleanup(
                status: Any,
                *,
                current_player: Any = player,
                current_event: str = event_name,
            ) -> None:

                try:
                    from PySide6.QtMultimedia import (
                        QMediaPlayer,
                    )

                    if status in (
                        QMediaPlayer.MediaStatus.EndOfMedia,
                        QMediaPlayer.MediaStatus.InvalidMedia,
                    ):
                        with self._lock:
                            current = self._players.get(
                                current_event
                            )

                            if (
                                current is not None
                                and current[0]
                                is current_player
                            ):
                                self._players.pop(
                                    current_event,
                                    None,
                                )

                        try:
                            current_player.stop()
                        except Exception:
                            pass

                except Exception:
                    logger.debug(
                        "Audio cleanup failed",
                        exc_info=True,
                    )

            player.mediaStatusChanged.connect(
                cleanup
            )

            # ----------------------------------------------------------
            # Error handling.
            # ----------------------------------------------------------

            def handle_error(
                error: Any,
                error_string: str,
                *,
                current_player: Any = player,
                current_event: str = event_name,
            ) -> None:

                if error:
                    logger.warning(
                        "Audio playback error for %s: %s",
                        current_event,
                        error_string,
                    )

                with self._lock:
                    current = self._players.get(
                        current_event
                    )

                    if (
                        current is not None
                        and current[0]
                        is current_player
                    ):
                        self._players.pop(
                            current_event,
                            None,
                        )

            try:
                player.errorOccurred.connect(
                    handle_error
                )
            except Exception:
                logger.debug(
                    "Could not attach audio error callback",
                    exc_info=True,
                )

            # ----------------------------------------------------------
            # Start playback.
            # ----------------------------------------------------------

            player.play()

            logger.info(
                "Playing custom sound: %s -> %s",
                event_name,
                path,
            )

            return True

        except Exception as exc:
            logger.warning(
                "Unable to play sound %s: %s",
                path,
                exc,
                exc_info=True,
            )

            with self._lock:
                self._players.pop(
                    event_name,
                    None,
                )

            return False

    # ==================================================================
    # STOP ONE SOUND
    # ==================================================================

    def stop_event_sound(
        self,
        event_name: str,
    ) -> None:
        """
        Stop a currently playing event sound.
        """

        with self._lock:
            current = self._players.pop(
                event_name,
                None,
            )

        if current is None:
            return

        player, _audio_output = current

        try:
            player.stop()
        except Exception:
            logger.debug(
                "Unable to stop sound: %s",
                event_name,
                exc_info=True,
            )

    # ==================================================================
    # STOP ALL SOUNDS
    # ==================================================================

    def stop_all(self) -> None:
        """
        Stop every currently playing sound.
        """

        with self._lock:
            players = list(
                self._players.values()
            )

            self._players.clear()

        for player, _audio_output in players:
            try:
                player.stop()
            except Exception:
                logger.debug(
                    "Unable to stop audio player",
                    exc_info=True,
                )

    # ==================================================================
    # MUTE
    # ==================================================================

    def set_muted(
        self,
        muted: bool,
    ) -> None:
        """
        Dynamically mute/unmute audio.
        """

        self.settings.muted = bool(
            muted
        )

        if self.settings.muted:
            self.stop_all()

    # ==================================================================
    # ENABLE / DISABLE
    # ==================================================================

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:
        """
        Dynamically enable/disable audio.
        """

        self.settings.enabled = bool(
            enabled
        )

        if not self.settings.enabled:
            self.stop_all()

    # ==================================================================
    # VOLUME
    # ==================================================================

    def set_volume(
        self,
        volume: float,
    ) -> None:
        """
        Set master volume from 0.0 to 1.0.
        """

        self.settings.master_volume = max(
            0.0,
            min(
                1.0,
                float(volume),
            ),
        )

        with self._lock:
            players = list(
                self._players.values()
            )

        for _player, audio_output in players:
            try:
                audio_output.setVolume(
                    self.settings.master_volume
                )
            except Exception:
                logger.debug(
                    "Unable to update audio volume",
                    exc_info=True,
                )

    # ==================================================================
    # AUDIO ENABLE CHECK
    # ==================================================================

    def _audio_enabled(self) -> bool:
        try:
            return bool(
                self.settings.enabled
            ) and not bool(
                self.settings.muted
            )

        except AttributeError:
            return False

    # ==================================================================
    # FALLBACK WINDOWS BEEP
    # ==================================================================

    def _beep(
        self,
        event_name: str,
    ) -> bool:
        """
        Windows fallback beep.

        This is only used when the corresponding custom sound
        cannot be played.
        """

        try:
            import winsound

            tones = {
                "SESSION_START": (
                    900,
                    250,
                ),

                "PHONE_DETECTED": (
                    1150,
                    240,
                ),

                "DROWSINESS": (
                    950,
                    260,
                ),

                "LOOKING_AWAY": (
                    760,
                    220,
                ),

                "BAD_POSTURE": (
                    680,
                    180,
                ),

                "YAWN": (
                    620,
                    160,
                ),

                "EXCESSIVE_BLINKING": (
                    820,
                    180,
                ),

                "USER_AWAY": (
                    700,
                    220,
                ),

                "USER_RETURNED": (
                    850,
                    180,
                ),

                "SESSION_END": (
                    600,
                    400,
                ),
            }

            frequency, duration = tones.get(
                event_name,
                (
                    800,
                    180,
                ),
            )

            winsound.Beep(
                frequency,
                duration,
            )

            logger.info(
                "Played fallback beep: %s",
                event_name,
            )

            return True

        except Exception:
            logger.info(
                "Audio alert: %s",
                event_name,
            )

            return False

    # ==================================================================
    # CLEANUP
    # ==================================================================

    def cleanup(self) -> None:
        """
        Release all audio resources.
        """

        self.stop_all()

        self._initialized = False
        self._qt_available = False