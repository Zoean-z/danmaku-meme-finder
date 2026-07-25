"""SQLite persistence for raw danmaku and aggregate queries."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import StoredDanmaku

SHANGHAI = ZoneInfo("Asia/Shanghai")

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_danmaku (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    normalized_content TEXT NOT NULL,
    user_key TEXT,
    sent_at TEXT NOT NULL,
    collected_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_danmaku_room_sent ON raw_danmaku(room_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_raw_danmaku_room_normalized ON raw_danmaku(room_id, normalized_content);
"""


def iso_now() -> datetime:
    return datetime.now(SHANGHAI)


class DanmakuDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def open(self) -> "DanmakuDatabase":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(SCHEMA)
        return self

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __enter__(self) -> "DanmakuDatabase":
        return self.open()

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("Database is not open")
        return self.connection

    def insert_many(self, messages: list[StoredDanmaku]) -> int:
        if not messages:
            return 0
        values = [
            (message.room_id, message.content, message.normalized_content, message.user_key,
             message.sent_at.isoformat(), message.collected_at.isoformat())
            for message in messages
        ]
        with self.conn:
            self.conn.executemany(
                """INSERT INTO raw_danmaku
                (room_id, content, normalized_content, user_key, sent_at, collected_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                values,
            )
        return len(values)

    def aggregate_since(self, room_id: int, start: datetime) -> tuple[int, list[sqlite3.Row]]:
        self.conn.row_factory = sqlite3.Row
        raw_count = self.conn.execute(
            "SELECT COUNT(*) FROM raw_danmaku WHERE room_id = ? AND sent_at >= ?",
            (room_id, start.isoformat()),
        ).fetchone()[0]
        rows = self.conn.execute(
            """SELECT normalized_content, MIN(content) AS text, COUNT(*) AS count,
                      COUNT(DISTINCT user_key) AS unique_users,
                      MIN(sent_at) AS first_seen_at, MAX(sent_at) AS last_seen_at
               FROM raw_danmaku
               WHERE room_id = ? AND sent_at >= ?
               GROUP BY normalized_content""",
            (room_id, start.isoformat()),
        ).fetchall()
        return int(raw_count), rows

    def stats(self, room_id: int) -> dict[str, object]:
        start = iso_now() - timedelta(hours=24)
        total = self.conn.execute("SELECT COUNT(*) FROM raw_danmaku WHERE room_id = ?", (room_id,)).fetchone()[0]
        recent = self.conn.execute(
            "SELECT COUNT(*) FROM raw_danmaku WHERE room_id = ? AND sent_at >= ?", (room_id, start.isoformat())
        ).fetchone()[0]
        unique = self.conn.execute(
            "SELECT COUNT(DISTINCT normalized_content) FROM raw_danmaku WHERE room_id = ? AND sent_at >= ?",
            (room_id, start.isoformat()),
        ).fetchone()[0]
        last = self.conn.execute("SELECT MAX(sent_at) FROM raw_danmaku WHERE room_id = ?", (room_id,)).fetchone()[0]
        return {"total": total, "recent": recent, "unique": unique, "last": last}
