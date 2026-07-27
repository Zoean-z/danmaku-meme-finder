from datetime import timedelta
from pathlib import Path

from danmaku_meme_finder.aggregate import build_candidates, deduplicate_similar_candidates
from danmaku_meme_finder.database import DanmakuDatabase, iso_now
from danmaku_meme_finder.exporter import write_json_atomic
from danmaku_meme_finder.models import StoredDanmaku


def message(
    content: str, minutes_ago: int, user_key: str | None = "u", session_id: str | None = None
) -> StoredDanmaku:
    now = iso_now()
    return StoredDanmaku(
        room_id=6657, content=content, normalized_content=content.lower(), user_key=user_key,
        session_id=session_id, sent_at=now - timedelta(minutes=minutes_ago), collected_at=now,
    )


def test_candidate_rules_existing_filter_and_stable_order(tmp_path: Path) -> None:
    database_path = tmp_path / "danmaku.db"
    existing_path = tmp_path / "existing.json"
    write_json_atomic(existing_path, {"items": {"old meme": {"id": 1}}})
    with DanmakuDatabase(database_path) as database:
        database.insert_many([
            message("new meme", 10, "a"), message("new meme", 9, "b"), message("new meme", 8, "c"),
            message("old meme", 7, "d"), message("old meme", 6, "e"), message("old meme", 5, "f"),
            message("这是一条足够长的低频候选文本用于测试并确保超过二十个字符", 4, "z"), message("!!!", 3),
        ])
        first = build_candidates(database, 6657, 24, 3, 200, existing_path)
        second = build_candidates(database, 6657, 24, 3, 200, existing_path)

    assert first["existingFilteredCount"] == 1
    assert [item["normalizedText"] for item in first["candidates"]] == [
        "new meme", "这是一条足够长的低频候选文本用于测试并确保超过二十个字符"
    ]
    assert first["candidates"][0]["source"] == "high_frequency"
    assert first["candidates"][1]["source"] == "long_text"
    assert first["candidates"] == second["candidates"]


def test_candidate_rules_exclude_short_and_activity_texts(tmp_path: Path) -> None:
    database_path = tmp_path / "danmaku.db"
    existing_path = tmp_path / "existing.json"
    write_json_atomic(existing_path, {"items": {}})
    with DanmakuDatabase(database_path) as database:
        database.insert_many([
            message("tiny", 4, "a"), message("tiny", 3, "b"), message("tiny", 2, "c"),
            message("保卫鱼娘", 4, "d"), message("保卫鱼娘", 3, "e"), message("保卫鱼娘", 2, "f"),
            message("eligible phrase", 4, "g"), message("eligible phrase", 3, "h"), message("eligible phrase", 2, "i"),
        ])
        payload = build_candidates(database, 6657, 24, 3, 200, existing_path)

    assert payload["shortFilteredCount"] == 1
    assert payload["activityFilteredCount"] == 1
    assert [candidate["text"] for candidate in payload["candidates"]] == ["eligible phrase"]


def test_candidate_keeps_exact_session_occurrences(tmp_path: Path) -> None:
    database_path = tmp_path / "danmaku.db"
    existing_path = tmp_path / "existing.json"
    write_json_atomic(existing_path, {"items": {}})
    with DanmakuDatabase(database_path) as database:
        database.insert_many([
            message("session meme", 4, "a", "session-a"),
            message("session meme", 3, "b", "session-a"),
            message("session meme", 2, "c", "session-b"),
        ])
        payload = build_candidates(database, 6657, 24, 3, 200, existing_path)

    occurrences = payload["candidates"][0]["collectionOccurrences"]
    assert [(item["sessionId"], item["count"]) for item in occurrences] == [
        ("session-a", 2),
        ("session-b", 1),
    ]


def test_candidate_rules_exclude_local_confirmed_memes(tmp_path: Path) -> None:
    database_path = tmp_path / "danmaku.db"
    existing_path = tmp_path / "existing.json"
    memes_path = tmp_path / "memes.json"
    write_json_atomic(existing_path, {"items": {}})
    write_json_atomic(memes_path, {"memes": [{"text": "confirmed local meme"}]})
    with DanmakuDatabase(database_path) as database:
        database.insert_many([
            message("confirmed local meme", 4, "a"),
            message("confirmed local meme", 3, "b"),
            message("confirmed local meme", 2, "c"),
            message("new eligible phrase", 4, "d"),
            message("new eligible phrase", 3, "e"),
            message("new eligible phrase", 2, "f"),
        ])
        payload = build_candidates(database, 6657, 24, 3, 200, existing_path, memes_path=memes_path)

    assert payload["localMemeFilteredCount"] == 1
    assert [candidate["text"] for candidate in payload["candidates"]] == ["new eligible phrase"]


def test_similar_candidates_keep_first_ranked_representative() -> None:
    candidates = [
        {
            "text": "赢不了图二为什么要赢图一？",
            "normalizedText": "赢不了图二为什么要赢图一?",
            "count": 10,
            "uniqueUsers": 8,
        },
        {
            "text": "赢不了图二为什么要赢图一😅赢不了图二为什么要赢图一😅",
            "normalizedText": "赢不了图二为什么要赢图一😅赢不了图二为什么要赢图一😅",
            "count": 3,
            "uniqueUsers": 2,
        },
        {
            "text": "让一让，草船来了",
            "normalizedText": "让一让,草船来了",
            "count": 6,
            "uniqueUsers": 5,
        },
    ]

    deduplicated, merged = deduplicate_similar_candidates(candidates, 0.88)

    assert merged == 1
    assert len(deduplicated) == 2
    assert deduplicated[0]["text"] == candidates[0]["text"]
    assert deduplicated[0]["similarVariants"] == [
        {
            "text": candidates[1]["text"],
            "normalizedText": candidates[1]["normalizedText"],
            "count": 3,
            "uniqueUsers": 2,
        }
    ]
