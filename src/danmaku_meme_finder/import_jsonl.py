"""Import the Node collector's append-only JSONL file into SQLite."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .collector import make_stored
from .database import SHANGHAI, DanmakuDatabase
from .exporter import read_json, write_json_atomic
from .models import IncomingDanmaku, StoredDanmaku

LOGGER = logging.getLogger(__name__)


def _checkpoint_offset(path: Path) -> int:
    payload = read_json(path, {"offset": 0})
    try:
        offset = int(payload.get("offset", 0))
    except (AttributeError, TypeError, ValueError):
        return 0
    return max(offset, 0)


def _write_checkpoint(path: Path, offset: int) -> None:
    write_json_atomic(path, {"offset": offset, "updatedAt": datetime.now(SHANGHAI).isoformat()})


def _parse_record(raw: bytes) -> IncomingDanmaku:
    payload: Any = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSONL record must be an object")
    text = payload.get("text")
    if not isinstance(text, str) or not text:
        raise ValueError("JSONL record text must be a non-empty string")
    room_id = int(payload["roomId"])
    if room_id <= 0:
        raise ValueError("JSONL record roomId must be positive")
    timestamp = datetime.fromisoformat(str(payload["ts"]).replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=SHANGHAI)
    else:
        timestamp = timestamp.astimezone(SHANGHAI)
    uid = payload.get("uid")
    session_id = payload.get("sessionId")
    if session_id is not None and (not isinstance(session_id, str) or not session_id.strip()):
        raise ValueError("JSONL record sessionId must be a non-empty string when provided")
    return IncomingDanmaku(
        room_id=room_id,
        content=text,
        user_id=None if uid is None else str(uid),
        session_id=session_id,
        sent_at=timestamp,
    )


def import_jsonl(
    input_path: Path,
    checkpoint_path: Path,
    database: DanmakuDatabase,
    salt: str,
    batch_size: int = 100,
) -> dict[str, int]:
    """Import complete new lines only and checkpoint each committed byte offset."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if not input_path.is_file():
        return {"imported": 0, "skipped": 0, "offset": _checkpoint_offset(checkpoint_path)}

    start_offset = min(_checkpoint_offset(checkpoint_path), input_path.stat().st_size)
    offset = start_offset
    safe_offset = start_offset
    pending: list[StoredDanmaku] = []
    imported = 0
    skipped = 0

    def flush() -> None:
        nonlocal imported, offset
        imported += database.insert_many(pending)
        pending.clear()
        _write_checkpoint(checkpoint_path, safe_offset)
        offset = safe_offset

    with input_path.open("rb") as handle:
        handle.seek(start_offset)
        while True:
            line_start = handle.tell()
            raw_line = handle.readline()
            if not raw_line:
                break
            line_end = handle.tell()
            if not raw_line.endswith(b"\n"):
                LOGGER.info("Ignoring incomplete trailing JSONL line at byte %s", line_start)
                break
            safe_offset = line_end
            try:
                pending.append(make_stored(_parse_record(raw_line), salt))
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                skipped += 1
                LOGGER.warning("Skipping malformed JSONL record at byte %s: %s", line_start, exc)
            if len(pending) >= batch_size:
                flush()
            elif not pending and safe_offset > offset:
                # Persist progress across malformed records without revisiting them forever.
                _write_checkpoint(checkpoint_path, safe_offset)
                offset = safe_offset
        if pending:
            flush()
        elif safe_offset > offset:
            _write_checkpoint(checkpoint_path, safe_offset)
            offset = safe_offset
    return {"imported": imported, "skipped": skipped, "offset": offset}
