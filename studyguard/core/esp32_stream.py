"""Low-latency TCP JPEG stream server for the FocusForge ESP32-S3.

Wire protocol: 4-byte unsigned big-endian JPEG length, followed by JPEG bytes.
The ESP32 connects as a TCP client to the Windows computer on port 8080.
"""
from __future__ import annotations

import logging
import socket
import struct
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class ESP32StreamServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        width: int = 320,
        height: int = 240,
        fps: float = 4.0,
        jpeg_quality: int = 55,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.width = int(width)
        self.height = int(height)
        self.fps = max(1.0, float(fps))
        self.jpeg_quality = max(20, min(95, int(jpeg_quality)))

        self._stop_event = threading.Event()
        self._frame_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_frame: Any = None
        self._server_socket: socket.socket | None = None
        self._client_socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._last_submit = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="FocusForge-ESP32-TCP",
            daemon=True,
        )
        self._thread.start()

    def submit_frame(self, frame: Any) -> None:
        """Keep only the newest frame; never block the GUI on network I/O."""
        now = time.monotonic()
        if now - self._last_submit < (1.0 / self.fps):
            return
        self._last_submit = now
        with self._frame_lock:
            self._latest_frame = frame
        self._frame_event.set()

    def _run(self) -> None:
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket = server
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, self.port))
            server.listen(1)
            server.settimeout(0.5)
            logger.info(
                "FocusForge ESP32 TCP stream listening on %s:%s",
                self.host,
                self.port,
            )
            print(f"[ESP32 STREAM] Listening on TCP port {self.port}", flush=True)

            while not self._stop_event.is_set():
                try:
                    client, address = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                self._client_socket = client
                logger.info("ESP32 stream client connected: %s", address)
                print(f"[ESP32 STREAM] ESP32 connected: {address}", flush=True)
                client.settimeout(2.0)

                try:
                    self._send_frames(client)
                except (ConnectionError, OSError, socket.timeout) as exc:
                    logger.info("ESP32 stream client disconnected: %s", exc)
                finally:
                    try:
                        client.close()
                    except OSError:
                        pass
                    self._client_socket = None

        except OSError:
            logger.exception(
                "Could not start ESP32 TCP stream server on port %s",
                self.port,
            )
            print(
                f"[ESP32 STREAM] ERROR: Could not listen on port {self.port}. "
                "Check whether another process is using it.",
                flush=True,
            )
        finally:
            if self._server_socket is not None:
                try:
                    self._server_socket.close()
                except OSError:
                    pass
                self._server_socket = None

    def _send_frames(self, client: socket.socket) -> None:
        import cv2

        interval = 1.0 / self.fps
        while not self._stop_event.is_set():
            self._frame_event.wait(timeout=0.5)
            if self._stop_event.is_set():
                return

            with self._frame_lock:
                frame = self._latest_frame
                self._frame_event.clear()

            if frame is None:
                continue

            resized = cv2.resize(
                frame,
                (self.width, self.height),
                interpolation=cv2.INTER_AREA,
            )
            ok, encoded = cv2.imencode(
                ".jpg",
                resized,
                [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
            )
            if not ok:
                continue

            payload = encoded.tobytes()
            if not payload or len(payload) > 1_500_000:
                continue

            # Matches the ESP32 receiver: 4-byte big-endian length + JPEG.
            client.sendall(struct.pack(">I", len(payload)))
            client.sendall(payload)

            # Limit output rate and avoid flooding the ESP32.
            self._stop_event.wait(interval)

    def stop(self) -> None:
        self._stop_event.set()
        self._frame_event.set()

        for sock in (self._client_socket, self._server_socket):
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    sock.close()
                except OSError:
                    pass

        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None
