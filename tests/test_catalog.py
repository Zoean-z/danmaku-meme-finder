from danmaku_meme_finder.catalog import build_catalog, format_catalog_id


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
            {"id": "local-1", "text": "same meme", "tags": ["24"], "addedAt": "2026-07-25T12:00:00+08:00"},
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
