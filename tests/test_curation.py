import pytest

from danmaku_meme_finder.curation import add_confirmed_meme, parse_tags, resolve_tags, tag_labels


def test_add_confirmed_meme_assigns_id_and_tags() -> None:
    memes, created = add_confirmed_meme(
        {"roomId": 6657, "memes": []},
        {"text": "New Meme", "normalizedText": "new meme"},
        ["24", "06"],
        "22025",
    )

    assert created is True
    assert memes["memes"] == [{
        "id": "22025",
        "text": "New Meme",
        "tags": ["24", "06"],
        "addedAt": memes["memes"][0]["addedAt"],
    }]


def test_add_confirmed_meme_merges_tags_for_same_normalized_text() -> None:
    memes = {"memes": [{"id": "22025", "text": "New Meme", "tags": ["06"]}]}
    updated, created = add_confirmed_meme(
        memes,
        {"text": " new   meme ", "normalizedText": "new meme"},
        parse_tags("24,06"),
        "22026",
    )

    assert created is False
    assert updated["memes"] == [{"id": "22025", "text": "New Meme", "tags": ["06", "24"]}]


def test_tag_resolution_accepts_codes_labels_and_full_width_commas() -> None:
    labels = tag_labels({"tags": {"06": {"label": "群魔乱舞"}, "24": {"label": "HLTV"}}})

    assert resolve_tags("HLTV，06", labels) == ["06", "24"]
    with pytest.raises(ValueError, match="unknown tag"):
        resolve_tags("不存在", labels)
