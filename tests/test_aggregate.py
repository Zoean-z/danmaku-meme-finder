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
    assert deduplicated[0]["familyCount"] == 13
    assert deduplicated[0]["similarVariants"] == [
        {
            "text": candidates[1]["text"],
            "normalizedText": candidates[1]["normalizedText"],
            "count": 3,
            "uniqueUsers": 2,
        }
    ]


def test_default_candidate_deduplication_strips_mentions_and_activity_copy(tmp_path: Path) -> None:
    database_path = tmp_path / "danmaku.db"
    existing_path = tmp_path / "existing.json"
    write_json_atomic(existing_path, {"items": {}})
    with DanmakuDatabase(database_path) as database:
        database.insert_many([
            message("@忍野忍：甜甜圈一个甜甜圈两个甜甜圈三个", 6, "a"),
            message("@忍野忍：甜甜圈一个甜甜圈两个甜甜圈三个", 5, "b"),
            message("@忍野忍：甜甜圈一个甜甜圈两个甜甜圈三个", 4, "c"),
            message("甜甜圈一个甜甜圈两个甜甜圈三个", 3, "d"),
            message("甜甜圈一个甜甜圈两个甜甜圈三个", 2, "e"),
            message("甜甜圈一个甜甜圈两个甜甜圈三个", 1, "f"),
            message("保卫男娘查看活动》", 3, "g"),
            message("保卫男娘查看活动》", 2, "h"),
            message("保卫男娘查看活动》", 1, "i"),
            message("@rain：？", 3, "j"),
            message("@rain：？", 2, "k"),
            message("@rain：？", 1, "l"),
            message("#显示猪头", 3, "m"),
            message("#显示猪头", 2, "n"),
            message("#显示猪头", 1, "o"),
        ])
        payload = build_candidates(database, 6657, 24, 3, 20, existing_path)

    assert len(payload["candidates"]) == 1
    assert payload["candidates"][0]["familyCount"] == 6
    assert payload["similarityDeduplication"]["mergedCandidates"] == 1
    assert payload["activityFilteredCount"] == 2
    assert payload["meaninglessFilteredCount"] == 1


def test_candidate_family_evidence_affects_final_ranking() -> None:
    candidates = [
        {"text": "standalone phrase", "normalizedText": "standalone phrase", "count": 5, "uniqueUsers": 5},
        {"text": "template phrase one", "normalizedText": "template phrase one", "count": 4, "uniqueUsers": 4},
        {"text": "@user：template phrase one", "normalizedText": "@user:template phrase one", "count": 4, "uniqueUsers": 3},
    ]

    deduplicated, merged = deduplicate_similar_candidates(candidates, 0.82)

    assert merged == 1
    assert deduplicated[0]["text"] == "template phrase one"
    assert deduplicated[0]["familyCount"] == 8


def test_candidate_filters_variants_of_previously_rejected_text(tmp_path: Path) -> None:
    database_path = tmp_path / "danmaku.db"
    existing_path = tmp_path / "existing.json"
    review_state_path = tmp_path / "review-state.json"
    write_json_atomic(existing_path, {"items": {}})
    write_json_atomic(review_state_path, {
        "rejected": {"机器你在哪里家里进白字了": {
            "text": "机器你在哪里家里进白字了", "excludeSimilar": True
        }}
    })
    with DanmakuDatabase(database_path) as database:
        database.insert_many([
            message("机器你在哪里？家里进白字了喵", 3, "a"),
            message("机器你在哪里？家里进白字了喵", 2, "b"),
            message("机器你在哪里？家里进白字了喵", 1, "c"),
        ])
        payload = build_candidates(
            database,
            6657,
            24,
            3,
            20,
            existing_path,
            review_state_path=review_state_path,
        )

    assert payload["candidates"] == []
    assert payload["reviewedSimilarFilteredCount"] == 1


def test_plain_rejection_only_filters_exact_text(tmp_path: Path) -> None:
    database_path = tmp_path / "danmaku.db"
    existing_path = tmp_path / "existing.json"
    review_state_path = tmp_path / "review-state.json"
    write_json_atomic(existing_path, {"items": {}})
    write_json_atomic(review_state_path, {
        "rejected": {"我爱你玩机器": {"text": "我爱你玩机器", "excludeSimilar": False}}
    })
    with DanmakuDatabase(database_path) as database:
        database.insert_many([
            message("我爱你刘帅宇", 3, "a"),
            message("我爱你刘帅宇", 2, "b"),
            message("我爱你刘帅宇", 1, "c"),
        ])
        payload = build_candidates(
            database, 6657, 24, 3, 20, existing_path, review_state_path=review_state_path
        )

    assert [candidate["text"] for candidate in payload["candidates"]] == ["我爱你刘帅宇"]


def test_similar_family_block_filters_template_and_numeric_variants(tmp_path: Path) -> None:
    database_path = tmp_path / "danmaku.db"
    existing_path = tmp_path / "existing.json"
    review_state_path = tmp_path / "review-state.json"
    write_json_atomic(existing_path, {"items": {}})
    write_json_atomic(review_state_path, {
        "rejected": {
            "我爱你玩机器": {"text": "我爱你玩机器", "excludeSimilar": True},
            "草白看24局2024": {"text": "草，白看24局！（20／24）", "excludeSimilar": True},
        }
    })
    with DanmakuDatabase(database_path) as database:
        database.insert_many([
            message("我爱你刘帅宇", 4, "a"), message("我爱你刘帅宇", 3, "b"),
            message("我爱你刘帅宇", 2, "c"), message("草！白看24局！", 4, "d"),
            message("草！白看24局！", 3, "e"), message("草！白看24局！", 2, "f"),
        ])
        payload = build_candidates(
            database, 6657, 24, 3, 20, existing_path, review_state_path=review_state_path
        )

    assert payload["candidates"] == []
    assert payload["reviewedSimilarFilteredCount"] == 2


def test_candidate_filters_variants_of_existing_catalog_text(tmp_path: Path) -> None:
    database_path = tmp_path / "danmaku.db"
    existing_path = tmp_path / "existing.json"
    write_json_atomic(existing_path, {
        "items": {"机器你在哪里家里进白字了": {"id": 1}}
    })
    with DanmakuDatabase(database_path) as database:
        database.insert_many([
            message("@major：机器你在哪里？家里进白字了喵", 3, "a"),
            message("@major：机器你在哪里？家里进白字了喵", 2, "b"),
            message("@major：机器你在哪里？家里进白字了喵", 1, "c"),
        ])
        payload = build_candidates(database, 6657, 24, 3, 20, existing_path)

    assert payload["candidates"] == []
    assert payload["existingSimilarFilteredCount"] == 1
