from danmaku_meme_finder.review_state import reject_candidate, review_queue


def test_review_queue_hides_confirmed_and_rejected_candidates() -> None:
    candidates = [
        {"text": "confirmed", "normalizedText": "confirmed"},
        {"text": "rejected", "normalizedText": "rejected"},
        {"text": "next", "normalizedText": "next"},
    ]
    memes = {"memes": [{"text": "confirmed"}]}
    state: dict[str, object] = {"rejected": {}}
    reject_candidate(state, candidates[1])

    assert review_queue(candidates, memes, state) == [candidates[2]]


def test_reject_candidate_can_persist_similar_family_block() -> None:
    state: dict[str, object] = {"rejected": {}}

    reject_candidate(
        state,
        {"text": "我爱你玩机器", "normalizedText": "我爱你玩机器"},
        exclude_similar=True,
    )

    assert state["rejected"]["我爱你玩机器"]["excludeSimilar"] is True  # type: ignore[index]
