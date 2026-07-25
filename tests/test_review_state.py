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
