from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from studyguard.analytics.focus_score import FocusScore
from studyguard.core.events import AppEvent
from studyguard.core.session import StudySession
from studyguard.database.db import Database


class Repository:
    def __init__(self, db: Database):
        self.db = db

    def create_session(self, session: StudySession) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO sessions(started_at, duration, focused_seconds, focus_score, best_streak) VALUES (?, 0, 0, 100, 0)",
                (session.started_at,),
            )
            return int(cur.lastrowid)

    def finish_session(self, session: StudySession, score: FocusScore) -> None:
        if session.id is None:
            return
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET ended_at=?, duration=?, focused_seconds=?, focus_score=?, best_streak=?
                WHERE id=?
                """,
                (session.ended_at, session.elapsed, session.focused_seconds, score.score, session.best_streak, session.id),
            )

    def add_event(self, session_id: int | None, event: AppEvent) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO events(session_id, timestamp, event_type, duration, confidence, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    event.timestamp,
                    event.event_type.value,
                    event.duration,
                    event.confidence,
                    json.dumps(event.metadata),
                ),
            )

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def set_setting(self, key: str, value: str) -> None:
        with self.db.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, value))

    def get_setting(self, key: str, default: str = "") -> str:
        with self.db.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def save_calibration(self, key: str, value: str, timestamp: float) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO calibration(key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, timestamp),
            )

    def clear_all(self) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM events")
            conn.execute("DELETE FROM sessions")
            conn.execute("DELETE FROM daily_statistics")
            conn.execute("DELETE FROM calibration")

    def export_sessions_csv(self, path: Path) -> None:
        rows = self.sessions(limit=100000)
        self._write_csv(path, rows)

    def export_events_csv(self, path: Path) -> None:
        with self.db.connect() as conn:
            rows = [dict(row) for row in conn.execute("SELECT * FROM events ORDER BY timestamp").fetchall()]
        self._write_csv(path, rows)

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = list(rows[0].keys()) if rows else ["empty"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def day_key(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
