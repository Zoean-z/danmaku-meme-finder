import json
from pathlib import Path

from danmaku_meme_finder.exporter import write_json_atomic


def test_atomic_json_export_has_expected_structure(tmp_path: Path) -> None:
    target = tmp_path / "candidates.json"
    payload = {"roomId": 6657, "candidates": [{"text": "测试", "count": 3}]}
    write_json_atomic(target, payload)
    assert json.loads(target.read_text(encoding="utf-8")) == payload
    assert not list(tmp_path.glob("*.tmp"))
