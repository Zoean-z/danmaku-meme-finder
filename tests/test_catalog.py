from danmaku_meme_finder.catalog import build_catalog, catalog_id


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
    assert same["id"] == catalog_id("same meme")
    assert same["key"] == "same meme"
    assert same["tags"] == ["06", "24"]
    assert same["sources"][0]["count"] == 75
    assert same["sources"][1] == {
        "kind": "local",
        "sourceId": "local-1",
        "addedAt": "2026-07-25T12:00:00+08:00",
    }
