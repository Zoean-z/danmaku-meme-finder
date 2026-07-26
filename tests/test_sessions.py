from datetime import datetime

from danmaku_meme_finder.sessions import begin_session, finish_session, parse_room_metadata


def test_parse_room_metadata_extracts_public_fields() -> None:
    page = '''<h1> Test Live &amp; More </h1><a href="/g/CS2">CS2</a>
    <img src="https://rpic.douyucdn.cn/asrpic/260724/6979222_src.avif/dy4">'''
    metadata = parse_room_metadata(6657, page, '{"rid":6979222}')

    assert metadata == {
        "roomId": 6657,
        "rid": 6979222,
        "title": "Test Live & More",
        "category": "CS2",
        "coverUrl": "https://rpic.douyucdn.cn/asrpic/260724/6979222_src.avif/dy4",
        "sourceUrl": "https://www.douyu.com/6657",
    }


def test_parse_room_metadata_uses_description_as_category_fallback() -> None:
    page = '<title>Example</title><meta name="description" content="主播带来最精彩的CS2直播">'

    metadata = parse_room_metadata(6657, page, '{"rid":6979222}')

    assert metadata["category"] == "CS2"


def test_session_lifecycle_uses_observed_times() -> None:
    payload: dict[str, object] = {"sessions": []}
    started = datetime.fromisoformat("2026-07-24T21:43:08+08:00")
    record = begin_session(payload, 6657, {"rid": 6979222, "title": "Test"}, started)
    finish_session(payload, record["id"], 12, datetime.fromisoformat("2026-07-24T21:58:08+08:00"))

    assert record["id"] == "6657-20260724-214308"
    assert record["date"] == "2026-07-24"
    assert payload["schemaVersion"] == 1
    assert payload["sessions"][0]["barrageCount"] == 12
    assert payload["sessions"][0]["memeCount"] == 0
    assert payload["sessions"][0]["messageCount"] == 12
    assert payload["sessions"][0]["observedEndedAt"] == "2026-07-24T21:58:08+08:00"
