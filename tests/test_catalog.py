from pathlib import Path

from danmaku_meme_finder.catalog import (
    build_catalog,
    build_daily_trends,
    build_hot_catalog,
    build_search_index,
    format_catalog_id,
    load_distributed_catalog,
    split_catalog,
    write_distributed_catalog,
)


def test_catalog_merges_sources_without_adding_counts() -> None:
    existing = {
        "total": 2,
        "items": {
            "same meme": {
                "id": 7,
                "barrage": "Same Meme",
                "cnt": 75,
                "tags": ["06"],
                "submitTime": "2026-07-22T08:48:18",
            }
        },
    }
    memes = {
        "memes": [
            {
                "id": "local-1",
                "text": "same meme",
                "tags": ["24"],
                "addedAt": "2026-07-25T12:00:00+08:00",
                "firstSeenAt": "2026-07-24T17:25:27+08:00",
                "lastSeenAt": "2026-07-24T19:25:27+08:00",
                "collectionOccurrences": [
                    {"sessionId": "session-a", "date": "2026-07-24", "count": 2}
                ],
            },
            {"text": "Local only", "tags": []},
        ]
    }

    catalog = build_catalog(existing, memes, 6657)

    assert catalog["summary"] == {
        "legacyRecords": 2,
        "legacyUniqueTexts": 1,
        "localRecords": 2,
        "mergedItems": 2,
    }
    same = catalog["items"][1]
    assert same["id"] == "00007"
    assert same["key"] == "same meme"
    assert same["tags"] == ["06", "24"]
    assert same["sources"][0]["count"] == 75
    assert same["sources"][1] == {
        "kind": "local",
        "sourceId": "local-1",
        "addedAt": "2026-07-25T12:00:00+08:00",
        "firstSeenAt": "2026-07-24T17:25:27+08:00",
        "lastSeenAt": "2026-07-24T19:25:27+08:00",
        "collectionOccurrences": [
            {"sessionId": "session-a", "date": "2026-07-24", "count": 2}
        ],
    }


def test_catalog_keeps_numeric_ids_from_the_previous_export() -> None:
    existing = {
        "total": 1,
        "items": {"same meme": {"id": 7, "barrage": "Same Meme", "cnt": 1, "tags": []}},
    }
    previous = {"items": [{"id": "00042", "key": "same meme"}]}

    catalog = build_catalog(existing, {"memes": []}, 6657, previous)

    assert catalog["schemaVersion"] == 2
    assert catalog["items"][0]["id"] == "00042"
    assert format_catalog_id(42) == "00042"


def test_catalog_splits_recent_three_months_from_archives() -> None:
    items = []
    for number, month in enumerate(("2026-07", "2026-06", "2026-05", "2026-04"), start=1):
        items.append(
            {
                "id": f"{number:05d}",
                "key": f"meme-{number}",
                "text": f"Meme {number}",
                "tags": ["06"],
                "sources": [{"kind": "legacy_api", "submittedAt": f"{month}-15T12:00:00", "count": number}],
            }
        )
    catalog = {"generatedAt": "2026-07-26T12:00:00+08:00", "roomId": 6657, "items": items}

    split = split_catalog(catalog)

    assert split["manifest"]["active"]["months"] == ["2026-05", "2026-06", "2026-07"]
    assert split["manifest"]["active"]["count"] == 3
    assert list(split["archives"]) == ["2026-04"]
    all_ids = {item["id"] for item in split["active"]["items"]}
    all_ids.update(item["id"] for document in split["archives"].values() for item in document["items"])
    assert all_ids == {"00001", "00002", "00003", "00004"}


def test_full_catalog_hot_and_search_outputs_include_archives() -> None:
    catalog = {
        "generatedAt": "2026-07-26T12:00:00+08:00",
        "roomId": 6657,
        "items": [
            {
                "id": "00002",
                "text": "Recent",
                "tags": ["06"],
                "sources": [{"submittedAt": "2026-07-01T00:00:00", "count": 2}],
            },
            {
                "id": "00001",
                "text": "Historic leader",
                "tags": ["24"],
                "sources": [{"submittedAt": "2024-01-01T00:00:00", "count": 99}],
            },
        ],
    }

    hot = build_hot_catalog(catalog, limit=1)
    search = build_search_index(catalog)

    assert hot["items"][0]["id"] == "00001"
    assert [item["id"] for item in search["items"]] == ["00001", "00002"]
    assert search["items"][0] == {
        "id": "00001",
        "text": "Historic leader",
        "tags": ["24"],
        "count": 99,
        "latestAt": "2024-01-01T00:00:00",
        "month": "2024-01",
    }


def test_distributed_catalog_round_trip_and_daily_trends(tmp_path: Path) -> None:
    catalog = {
        "generatedAt": "2026-07-26T12:00:00+08:00",
        "roomId": 6657,
        "items": [
            {
                "id": "00007",
                "key": "same meme",
                "text": "Same Meme",
                "tags": ["06", "24"],
                "sources": [
                    {"kind": "legacy_api", "submittedAt": "2026-04-15T12:00:00", "count": 75},
                    {"kind": "local", "lastSeenAt": "2026-07-24T19:25:27+08:00"},
                ],
            }
        ],
    }
    directory = tmp_path / "data" / "catalog"
    trends_path = tmp_path / "data" / "trends" / "daily.json"

    manifest = write_distributed_catalog(catalog, directory, trends_path)
    loaded = load_distributed_catalog(directory)
    trends = build_daily_trends(catalog)

    assert manifest["total"] == 1
    assert manifest["hot"] == {"file": "catalog/hot.json", "count": 1}
    assert manifest["search"] == {"file": "catalog/search-index.json", "count": 1}
    assert loaded["items"][0]["id"] == "00007"
    assert trends["points"] == [
        {"date": "2026-04-15", "memeCount": 1, "barrageCount": 75, "tagCounts": {"06": 1, "24": 1}},
        {"date": "2026-07-24", "memeCount": 1, "barrageCount": 1, "tagCounts": {"06": 1, "24": 1}},
    ]
    assert trends_path.is_file()
    assert (directory / "hot.json").is_file()
    assert (directory / "search-index.json").is_file()


def test_unchanged_archive_keeps_its_original_generated_time(tmp_path: Path) -> None:
    directory = tmp_path / "data" / "catalog"
    trends_path = tmp_path / "data" / "trends" / "daily.json"
    catalog = {
        "generatedAt": "2026-07-01T00:00:00+08:00",
        "roomId": 6657,
        "items": [
            {"id": "00001", "text": "Old", "sources": [{"submittedAt": "2025-01-01T00:00:00"}]},
            {"id": "00002", "text": "New", "sources": [{"submittedAt": "2026-07-01T00:00:00"}]},
        ],
    }
    write_distributed_catalog(catalog, directory, trends_path)
    archive_path = directory / "archive" / "2025-01.json"
    original = archive_path.read_text(encoding="utf-8")

    catalog["generatedAt"] = "2026-07-02T00:00:00+08:00"
    write_distributed_catalog(catalog, directory, trends_path)

    assert archive_path.read_text(encoding="utf-8") == original
