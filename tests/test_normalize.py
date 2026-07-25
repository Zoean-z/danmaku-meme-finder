from danmaku_meme_finder.normalize import has_meaningful_content, normalize_text


def test_normalize_text_applies_nfkc_spacing_case_and_punctuation() -> None:
    assert normalize_text("  ＨＥＬＬＯ　，　世界！！！  ") == "hello, 世界!!!"


def test_normalize_text_limits_repeated_characters_and_punctuation() -> None:
    assert normalize_text("哈哈哈哈哈哈!!!!!!") == "哈哈哈哈哈!!!"
    assert normalize_text("goooooooo") == "gooooo"


def test_meaningful_content_rejects_punctuation_and_emoji_only() -> None:
    assert not has_meaningful_content("!!! 😄")
    assert has_meaningful_content("😄 好")
