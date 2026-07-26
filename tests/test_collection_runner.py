import json
from pathlib import Path

from danmaku_meme_finder.collection_runner import (
    CollectionSettings,
    build_current_candidates,
    import_pending,
)
from danmaku_meme_finder.exporter import write_json_atomic


def test_import_and_candidate_build_keep_repeated_non_existing_text(tmp_path: Path) -> None:
    input_path = tmp_path / "live.jsonl"
    checkpoint_path = tmp_path / "checkpoint.json"
    existing_path = tmp_path / "existing.json"
    output_path = tmp_path / "candidates.json"
    records = [
        {"ts": f"2026-07-25T12:00:0{index}+08:00", "roomId": 6657, "uid": str(index), "text": "新梗模板文本"}
        for index in range(3)
    ] + [
        {"ts": f"2026-07-25T12:01:0{index}+08:00", "roomId": 6657, "uid": str(10 + index), "text": "已有梗"}
        for index in range(3)
    ]
    input_path.write_text("".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8")
    write_json_atomic(existing_path, {"items": {"已有梗": {"id": 1}}})
    settings = CollectionSettings(
        room_id=6657,
        database_path=tmp_path / "danmaku.db",
        input_path=input_path,
        checkpoint_path=checkpoint_path,
        existing_index_path=existing_path,
        output_path=output_path,
        similarity_threshold=None,
        window_hours=48,
    )

    result = import_pending(settings, "salt")
    candidates = build_current_candidates(settings)

    assert result["imported"] == 6
    assert [candidate["text"] for candidate in candidates["candidates"]] == ["新梗模板文本"]
    assert json.loads(output_path.read_text(encoding="utf-8"))["candidates"] == candidates["candidates"]
