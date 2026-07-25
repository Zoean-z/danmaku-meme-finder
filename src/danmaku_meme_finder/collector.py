"""Local message preparation shared by JSONL import and SQLite storage."""

from __future__ import annotations

import hashlib
from datetime import datetime

from .database import iso_now
from .models import IncomingDanmaku, StoredDanmaku
from .normalize import normalize_text


def _user_key(user_id: str | None, salt: str) -> str | None:
    if not user_id:
        return None
    return hashlib.sha256(f"{salt}:{user_id}".encode("utf-8")).hexdigest()


def make_stored(message: IncomingDanmaku, salt: str, collected_at: datetime | None = None) -> StoredDanmaku:
    return StoredDanmaku(
        room_id=message.room_id,
        content=message.content,
        normalized_content=normalize_text(message.content),
        user_key=_user_key(message.user_id, salt),
        sent_at=message.sent_at,
        collected_at=collected_at or iso_now(),
    )
