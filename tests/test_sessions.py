from datetime import datetime

from danmaku_meme_finder.database import DanmakuDatabase
from danmaku_meme_finder.models import StoredDanmaku
from danmaku_meme_finder.sessions import (
    begin_session,
    finish_session,
    parse_room_metadata,
    refresh_session_provenance,
)


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


def test_refresh_session_provenance_backfills_memes_and_counts(tmp_path) -> None:
    moment = datetime.fromisoformat("2026-07-24T21:43:08+08:00")
    sessions = {"sessions": [{"id": "session-a", "date": "2026-07-24", "title": "Test"}]}
    memes = {"memes": [{"id": "00001", "text": "Session Meme", "tags": ["06"]}]}
    with DanmakuDatabase(tmp_path / "danmaku.db") as database:
        database.insert_many([
            StoredDanmaku(
                room_id=6657,
                content="Session Meme",
                normalized_content="session meme",
                user_key="u",
                session_id="session-a",
                sent_at=moment,
                collected_at=moment,
            )
        ])
        updated = refresh_session_provenance(sessions, memes, database, 6657)

    assert updated == 1
    assert memes["memes"][0]["collectionOccurrences"][0]["sessionId"] == "session-a"
    assert sessions["sessions"][0]["memeCount"] == 1
    assert sessions["sessions"][0]["barrageCount"] == 1
    assert sessions["sessions"][0]["tagCodes"] == ["06"]


def test_refresh_session_provenance_assigns_recurring_meme_to_first_session_only() -> None:
    sessions = {
        "sessions": [
            {"id": "session-a", "date": "2026-07-30"},
            {"id": "session-b", "date": "2026-07-31"},
        ]
    }
    memes = {
        "memes": [{
            "id": "22073",
            "text": "孩孩𓀐𓂸尼尼",
            "tags": ["07", "22"],
            "collectionOccurrences": [
                {
                    "sessionId": "session-a",
                    "date": "2026-07-30",
                    "count": 1,
                    "firstSeenAt": "2026-07-30T21:25:15+08:00",
                },
                {
                    "sessionId": "session-b",
                    "date": "2026-07-31",
                    "count": 2,
                    "firstSeenAt": "2026-07-31T21:10:09+08:00",
                },
            ],
        }]
    }

    updated = refresh_session_provenance(sessions, memes, None, 6657)

    assert updated == 0
    assert sessions["sessions"][0]["memeCount"] == 1
    assert sessions["sessions"][0]["tagCodes"] == ["07", "22"]
    assert sessions["sessions"][1]["memeCount"] == 0
    assert sessions["sessions"][1]["tagCodes"] == []
    assert len(memes["memes"][0]["collectionOccurrences"]) == 2
