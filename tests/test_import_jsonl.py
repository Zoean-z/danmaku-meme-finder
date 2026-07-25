import json
from pathlib import Path

from danmaku_meme_finder.database import DanmakuDatabase
from danmaku_meme_finder.import_jsonl import import_jsonl


def test_import_jsonl_uses_checkpoint_and_hashes_uid(tmp_path: Path) -> None:
    source = tmp_path / "live.jsonl"
    checkpoint = tmp_path / "checkpoint.json"
    source.write_text(
        "\n".join([
            json.dumps({"ts": "2026-07-24T12:00:00+08:00", "roomId": 6657, "uid": "123", "text": "测试"}),
            json.dumps({"ts": "2026-07-24T12:01:00+08:00", "roomId": 6657, "uid": None, "text": "第二条"}),
            "",
        ]),
        encoding="utf-8",
    )
    with DanmakuDatabase(tmp_path / "danmaku.db") as database:
        first = import_jsonl(source, checkpoint, database, "salt", batch_size=2)
        second = import_jsonl(source, checkpoint, database, "salt", batch_size=2)
        rows = database.conn.execute("SELECT content, user_key FROM raw_danmaku ORDER BY id").fetchall()

    assert first["imported"] == 2
    assert second["imported"] == 0
    assert rows[0][0] == "测试"
    assert rows[0][1] != "123"
    assert rows[1][1] is None


def test_import_jsonl_waits_for_a_partial_trailing_line(tmp_path: Path) -> None:
    source = tmp_path / "live.jsonl"
    checkpoint = tmp_path / "checkpoint.json"
    complete = json.dumps({"ts": "2026-07-24T12:00:00+08:00", "roomId": 6657, "uid": "1", "text": "完成"}) + "\n"
    source.write_bytes(complete.encode("utf-8") + b'{"ts":"incomplete"')
    with DanmakuDatabase(tmp_path / "danmaku.db") as database:
        result = import_jsonl(source, checkpoint, database, "salt")
        count = database.conn.execute("SELECT COUNT(*) FROM raw_danmaku").fetchone()[0]

    assert result["imported"] == 1
    assert result["offset"] == len(complete.encode("utf-8"))
    assert count == 1
