import json
from pathlib import Path

import pytest

from danmaku_meme_finder.cleanup import cleanup_reviewed_sessions, reviewed_session_ids
from danmaku_meme_finder.database import DanmakuDatabase
from danmaku_meme_finder.import_jsonl import import_jsonl


def write_records(path: Path) -> None:
    records = [
        {"ts": "2026-08-01T10:00:00+08:00", "roomId": 6657, "uid": "1", "text": "session a text", "sessionId": "session-a"},
        {"ts": "2026-08-01T10:00:01+08:00", "roomId": 6657, "uid": "2", "text": "session b text", "sessionId": "session-b"},
    ]
    path.write_text("".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8")


def test_reviewed_session_ids_collects_snapshot_provenance() -> None:
    payload = {
        "candidates": [
            {"collectionOccurrences": [{"sessionId": "session-b"}, {"sessionId": "session-a"}]},
            {"collectionOccurrences": [{"sessionId": "session-a"}]},
        ]
    }

    assert reviewed_session_ids(payload) == {"session-a", "session-b"}


def test_cleanup_removes_only_explicit_fully_imported_sessions(tmp_path: Path) -> None:
    input_path = tmp_path / "live.jsonl"
    checkpoint_path = tmp_path / "checkpoint.json"
    database_path = tmp_path / "danmaku.db"
    write_records(input_path)
    with DanmakuDatabase(database_path) as database:
        assert import_jsonl(input_path, checkpoint_path, database, "salt")["imported"] == 2

    result = cleanup_reviewed_sessions(
        database_path, input_path, checkpoint_path, {"session-a"}
    )

    assert result == {
        "sessionIds": ["session-a"],
        "databaseMessagesRemoved": 1,
        "jsonlMessagesRemoved": 1,
        "jsonlMessagesKept": 1,
    }
    remaining = [json.loads(line) for line in input_path.read_text(encoding="utf-8").splitlines()]
    assert [record["sessionId"] for record in remaining] == ["session-b"]
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["offset"] == input_path.stat().st_size
    with DanmakuDatabase(database_path) as database:
        assert database.session_message_count("session-a") == 0
        assert database.session_message_count("session-b") == 1


def test_cleanup_refuses_jsonl_with_unimported_bytes(tmp_path: Path) -> None:
    input_path = tmp_path / "live.jsonl"
    checkpoint_path = tmp_path / "checkpoint.json"
    write_records(input_path)
    checkpoint_path.write_text('{"offset": 0}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="unimported"):
        cleanup_reviewed_sessions(
            tmp_path / "danmaku.db", input_path, checkpoint_path, {"session-a"}
        )
