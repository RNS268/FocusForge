"""
FocusForge AI bridge: StudyGuard (Windows) -> ESP32-S3 HTTP receiver.

Camera frames continue to use ESP32StreamServer on TCP port 8080.
This module sends timer snapshots and major distraction events to
http://<ESP32-IP>:8082/focus without blocking the Qt UI thread.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from studyguard.core.events import AppEvent, EventBus, EventType

logger = logging.getLogger(__name__)


class FocusForgeBridge:
    """Background HTTP bridge for ESP32 timer state and event updates."""

    MAJOR_EVENTS = {
        EventType.PHONE_DETECTED,
        EventType.LOOKING_AWAY,
        EventType.DROWSINESS,
        EventType.USER_AWAY,
    }

    def __init__(
        self,
        esp32_url: str,
        event_bus: EventBus,
        timeout: float = 2.0,
    ) -> None:
        self.esp32_url = esp32_url.rstrip("/")
        self.event_bus = event_bus
        self.timeout = float(timeout)

        self._events: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200)
        self._state_lock = threading.Lock()
        self._latest_state: dict[str, Any] | None = None
        self._last_state_publish = 0.0

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return

        self._stop_event.clear()
        self.event_bus.subscribe(self._on_event)

        self._thread = threading.Thread(
            target=self._worker,
            name="FocusForge-ESP32-Bridge",
            daemon=True,
        )
        self._thread.start()
        self._started = True
        logger.info("FocusForge ESP32 HTTP bridge started: %s", self.esp32_url)

    def _on_event(self, event: AppEvent) -> None:
        if event.event_type not in self.MAJOR_EVENTS:
            return

        payload = {
            "type": "event",
            "event": event.event_type.value,
            "event_id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "duration": max(0.0, float(event.duration)),
            "confidence": max(0.0, min(1.0, float(event.confidence))),
        }

        try:
            self._events.put_nowait(payload)
        except queue.Full:
            logger.warning("ESP32 event queue is full; event dropped: %s", payload["event"])

    def publish_state(
        self,
        *,
        session_state: str,
        session_elapsed_ms: int,
        distraction_count: int,
        pomodoro_enabled: bool,
        study_minutes: int,
        break_minutes: int,
        break_started_at: float | None,
        pomodoro_study_remaining_ms: int,
    ) -> None:
        """Queue the newest state snapshot; never performs network I/O here."""
        now = time.monotonic()
        if now - self._last_state_publish < 0.9:
            return
        self._last_state_publish = now

        session_state = str(session_state).upper()
        elapsed_ms = max(0, int(session_elapsed_ms))
        count = max(0, int(distraction_count))

        if not pomodoro_enabled:
            pomo_state = "OFF"
            remaining_ms = 0
        elif session_state == "BREAK":
            pomo_state = "BREAK"
            break_seconds = max(1, int(break_minutes)) * 60
            break_elapsed = (
                max(0.0, time.time() - break_started_at)
                if break_started_at is not None
                else 0.0
            )
            remaining_ms = max(0, int((break_seconds - break_elapsed) * 1000))
        elif session_state == "STUDYING":
            pomo_state = "RUNNING"
            remaining_ms = max(0, int(pomodoro_study_remaining_ms))
        elif session_state == "PAUSED":
            pomo_state = "PAUSED"
            remaining_ms = max(0, int(pomodoro_study_remaining_ms))
        else:
            pomo_state = "IDLE"
            remaining_ms = 0

        payload = {
            "type": "state",
            "session_state": session_state,
            "session_elapsed_ms": elapsed_ms,
            "distraction_count": count,
            "pomodoro_state": pomo_state,
            "pomodoro_remaining_ms": remaining_ms,
        }

        with self._state_lock:
            self._latest_state = payload

    def _post(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = Request(
            self.esp32_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            response.read()

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            payload: dict[str, Any] | None = None

            try:
                payload = self._events.get(timeout=0.15)
            except queue.Empty:
                pass

            if payload is None:
                with self._state_lock:
                    payload = self._latest_state
                    self._latest_state = None

            if payload is None:
                continue

            try:
                self._post(payload)
            except HTTPError as exc:
                try:
                    detail = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    detail = ""
                logger.warning("ESP32 HTTP sync failed: %s; response=%s", exc, detail)
            except (URLError, TimeoutError, OSError) as exc:
                logger.warning("ESP32 HTTP sync failed: %s", exc)
            except Exception:
                logger.exception("Unexpected ESP32 bridge error")
            finally:
                if "event_id" in payload:
                    self._events.task_done()

    def stop(self) -> None:
        if not self._started:
            return

        self.event_bus.unsubscribe(self._on_event)
        self._stop_event.set()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=self.timeout + 1.0)

        self._thread = None
        self._started = False
        logger.info("FocusForge ESP32 HTTP bridge stopped")
