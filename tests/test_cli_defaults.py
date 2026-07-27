from danmaku_meme_finder.aggregate import DEFAULT_SIMILARITY_THRESHOLD
from danmaku_meme_finder.cli import create_parser


def test_candidate_commands_default_to_twenty_deduplicated_items() -> None:
    parser = create_parser()

    for command in ("build-candidates", "collect", "collect-and-review"):
        args = parser.parse_args([command])
        assert args.max_candidates == 20
        assert args.similarity_threshold == DEFAULT_SIMILARITY_THRESHOLD
