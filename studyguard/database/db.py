from __future__ import annotations

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    ended_at REAL,
    duration REAL NOT NULL DEFAULT 0,
    focused_seconds REAL NOT NULL DEFAULT 0,
    focus_score INTEGER NOT NULL DEFAULT 100,
    best_streak REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,
    duration REAL NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 1,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_statistics (
    date TEXT PRIMARY KEY,
    study_seconds REAL NOT NULL DEFAULT 0,
    focus_seconds REAL NOT NULL DEFAULT 0,
    focus_score REAL NOT NULL DEFAULT 100,
    phone_events INTEGER NOT NULL DEFAULT 0,
    attention_events INTEGER NOT NULL DEFAULT 0,
    drowsiness_events INTEGER NOT NULL DEFAULT 0,
    posture_events INTEGER NOT NULL DEFAULT 0,
    best_streak REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS calibration (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        try:
            with self.connect() as conn:
                conn.executescript(SCHEMA)
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "disk i/o" not in message and "unable to open" not in message:
                raise
            logger.warning("SQLite disk initialization failed; using in-memory database: %s", exc)
            self._memory_conn = sqlite3.connect(":memory:")
            self._memory_conn.row_factory = sqlite3.Row
            self._memory_conn.executescript(SCHEMA)
