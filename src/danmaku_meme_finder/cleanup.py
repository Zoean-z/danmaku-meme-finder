"""Remove local raw evidence after a candidate snapshot is fully reviewed and published."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .database import SHANGHAI, DanmakuDatabase
from .exporter import read_json, write_json_atomic


def reviewed_session_ids(candidate_payload: dict[str, Any]) -> set[str]:
    """Return every concrete collection session represented by the snapshot."""
    session_ids: set[str] = set()
    candidates = candidate_payload.get("candidates", [])
    if not isinstance(candidates, list):
        return session_ids
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        occurrences = candidate.get("collectionOccurrences", [])
        if not isinstance(occurrences, list):
            continue
        for occurrence in occurrences:
            if not isinstance(occurrence, dict):
                continue
            session_id = occurrence.get("sessionId")
            if isinstance(session_id, str) and session_id.strip():
                session_ids.add(session_id.strip())
    return session_ids


def _checkpoint_offset(path: Path) -> int:
    payload = read_json(path, {"offset": 0})
    try:
        return max(0, int(payload.get("offset", 0)))
    except (AttributeError, TypeError, ValueError):
        return 0


def _build_pruned_jsonl(input_path: Path, session_ids: set[str]) -> tuple[Path, int, int]:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{input_path.name}.", suffix=".cleanup.tmp", dir=input_path.parent
    )
    removed = 0
    kept = 0
    try:
        with input_path.open("rb") as source, os.fdopen(descriptor, "wb") as target:
            for line in source:
                remove = False
                try:
                    payload = json.loads(line.decode("utf-8"))
                    remove = isinstance(payload, dict) and payload.get("sessionId") in session_ids
                except (UnicodeDecodeError, json.JSONDecodeError):
                    # Preserve malformed or incomplete evidence instead of deleting it by accident.
                    pass
                if remove:
                    removed += 1
                else:
                    target.write(line)
                    kept += 1
        return Path(temporary_name), removed, kept
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def cleanup_reviewed_sessions(
    database_path: Path,
    input_path: Path,
    checkpoint_path: Path,
    session_ids: set[str],
) -> dict[str, Any]:
    """Delete reviewed session rows from SQLite and the append-only local JSONL."""
    normalized_ids = {value.strip() for value in session_ids if value.strip()}
    if not normalized_ids:
        return {
            "sessionIds": [],
            "databaseMessagesRemoved": 0,
            "jsonlMessagesRemoved": 0,
            "jsonlMessagesKept": 0,
        }

    original_size = input_path.stat().st_size if input_path.is_file() else 0
    if input_path.is_file() and _checkpoint_offset(checkpoint_path) != original_size:
        raise ValueError("raw JSONL still has unimported data; cleanup was not started")

    temporary_path: Path | None = None
    backup_path = input_path.with_name(f".{input_path.name}.cleanup.backup")
    jsonl_removed = 0
    jsonl_kept = 0
    database_removed = 0
    try:
        if input_path.is_file():
            temporary_path, jsonl_removed, jsonl_kept = _build_pruned_jsonl(input_path, normalized_ids)
            if backup_path.exists():
                raise ValueError(f"cleanup backup already exists: {backup_path}")
            os.replace(input_path, backup_path)
            os.replace(temporary_path, input_path)
            temporary_path = None
            write_json_atomic(
                checkpoint_path,
                {"offset": input_path.stat().st_size, "updatedAt": datetime.now(SHANGHAI).isoformat()},
            )

        if database_path.is_file():
            with DanmakuDatabase(database_path) as database:
                database_removed = database.delete_sessions(normalized_ids)
    except Exception:
        if backup_path.is_file():
            if input_path.exists():
                input_path.unlink()
            os.replace(backup_path, input_path)
            write_json_atomic(
                checkpoint_path,
                {"offset": original_size, "updatedAt": datetime.now(SHANGHAI).isoformat()},
            )
        raise
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass

    if backup_path.is_file():
        backup_path.unlink()
    return {
        "sessionIds": sorted(normalized_ids),
        "databaseMessagesRemoved": database_removed,
        "jsonlMessagesRemoved": jsonl_removed,
        "jsonlMessagesKept": jsonl_kept,
    }
