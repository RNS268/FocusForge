from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import cv2

logger = logging.getLogger(__name__)


@dataclass
class AlarmState:
    last_sleep: float = 0.0
    last_face: float = 0.0
    last_phone: float = 0.0
    last_hand: float = 0.0


def beep(kind: str, alarms: AlarmState, cooldown: float = 4.0) -> None:
    now = time.time()
    last_attr = f"last_{kind}"
    if now - getattr(alarms, last_attr) < cooldown:
        return
    setattr(alarms, last_attr, now)
    try:
        import winsound

        tones = {
            "sleep": (950, 260),
            "face": (700, 220),
            "phone": (1150, 240),
            "hand": (820, 160),
        }
        freq, duration = tones.get(kind, (800, 180))
        winsound.Beep(freq, duration)
    except Exception:
        logger.info("Alert: %s", kind)


class SimplePhoneDetector:
    def __init__(self) -> None:
        self.model = None
        self.names = {}
        self.frame_count = 0
        self.last_box: tuple[int, int, int, int] | None = None
        self.last_conf = 0.0
        for path in [Path("models/yolov8n.pt"), Path("models/yolo11n.pt"), Path("assets/models/yolo11n.pt")]:
            if path.exists():
                try:
                    from ultralytics import YOLO

                    self.model = YOLO(str(path))
                    self.names = self.model.names
                    break
                except Exception as exc:
                    logger.warning("Could not load YOLO model %s: %s", path, exc)

    @property
    def available(self) -> bool:
        return self.model is not None

    def detect(self, frame) -> tuple[bool, tuple[int, int, int, int] | None, float]:
        if self.model is None:
            return False, None, 0.0
        self.frame_count += 1
        if self.frame_count % 6 != 0:
            return self.last_box is not None, self.last_box, self.last_conf
        detected = False
        best_conf = 0.0
        best_box = None
        results = self.model.predict(frame, verbose=False, conf=0.45, imgsz=416)
        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                name = str(self.names.get(cls_id, "")).lower()
                conf = float(box.conf[0])
                if name in {"cell phone", "mobile phone", "phone"} and conf > best_conf:
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    detected = True
                    best_conf = conf
                    best_box = (x1, y1, x2, y2)
        self.last_box = best_box if detected else None
        self.last_conf = best_conf if detected else 0.0
        return detected, self.last_box, self.last_conf


def draw_text(frame, text: str, xy: tuple[int, int], color=(0, 255, 255), scale=0.8, thickness=2) -> None:
    x, y = xy
    cv2.putText(frame, text, (x + 1, y + 1), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(frame, text, xy, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def draw_eye_outline(frame, eye_box: tuple[int, int, int, int], face_origin: tuple[int, int]) -> None:
    fx, fy = face_origin
    ex, ey, ew, eh = eye_box
    center = (fx + ex + ew // 2, fy + ey + eh // 2)
    axes = (max(14, ew // 2), max(8, eh // 2))
    cv2.ellipse(frame, center, axes, 0, 0, 360, (0, 255, 255), 3)


def detect_hand_near_camera(frame) -> bool:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower = (0, 25, 50)
    upper = (25, 220, 255)
    mask = cv2.inRange(hsv, lower, upper)
    mask = cv2.medianBlur(mask, 7)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return False
    largest = max(cv2.contourArea(c) for c in contours)
    return largest > frame.shape[0] * frame.shape[1] * 0.18


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    face_cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
    eye_cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_eye.xml"))
    phone_detector = SimplePhoneDetector()
    alarms = AlarmState()

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("Camera not available. Try closing other camera apps and run again.")
        return 1

    closed_frames = 0
    face_missing_frames = 0
    sleep_threshold_frames = 18
    face_missing_threshold_frames = 25
    window_name = "StudyGuard Simple"

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.2, 5, minSize=(120, 120))

        draw_text(frame, "StudyGuard Simple - press Q to quit", (20, 32), (0, 255, 255), 0.7, 2)
        draw_text(frame, "local webcam only", (20, 62), (120, 255, 180), 0.58, 1)

        sleepy = False
        face_hidden = False
        eyes_found = 0

        if len(faces):
            face_missing_frames = 0
            x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
            cv2.rectangle(frame, (x, y), (x + w, y + h), (80, 220, 80), 2)
            face_roi_gray = gray[y : y + h, x : x + w]
            eyes = eye_cascade.detectMultiScale(face_roi_gray, 1.1, 6, minSize=(22, 16))
            eyes = sorted(eyes, key=lambda e: e[2] * e[3], reverse=True)[:2]
            eyes_found = len(eyes)
            for eye in eyes:
                draw_eye_outline(frame, tuple(eye), (x, y))
            if eyes_found == 0:
                closed_frames += 1
            else:
                closed_frames = 0
            sleepy = closed_frames >= sleep_threshold_frames
        else:
            closed_frames = 0
            face_missing_frames += 1
            face_hidden = face_missing_frames >= face_missing_threshold_frames

        phone_detected, phone_box, phone_conf = phone_detector.detect(frame)
        if phone_box:
            x1, y1, x2, y2 = phone_box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 255), 3)
            draw_text(frame, f"phone {phone_conf:.0%}", (x1, max(28, y1 - 10)), (255, 0, 255), 0.7, 2)

        hand_close = detect_hand_near_camera(frame)

        if sleepy:
            draw_text(frame, "eyes closed! wake up :)", (40, 120), (0, 0, 255), 1.1, 3)
            beep("sleep", alarms)
        elif face_hidden:
            draw_text(frame, "face not visible", (40, 120), (0, 120, 255), 1.1, 3)
            beep("face", alarms)
        elif phone_detected:
            draw_text(frame, "put the phone away", (40, 120), (255, 0, 255), 1.1, 3)
            beep("phone", alarms)
        elif hand_close:
            draw_text(frame, "hand on camera?", (40, 120), (0, 200, 255), 1.0, 2)
            beep("hand", alarms, cooldown=7.0)
        else:
            draw_text(frame, f"eyes: {'open' if eyes_found else 'checking...'}", (40, 120), (0, 255, 0), 0.9, 2)

        if not phone_detector.available:
            draw_text(frame, "phone model missing: add models/yolov8n.pt", (20, frame.shape[0] - 20), (0, 200, 255), 0.55, 1)

        cv2.imshow(window_name, frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q") or key == ord("Q"):
            break

    cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
