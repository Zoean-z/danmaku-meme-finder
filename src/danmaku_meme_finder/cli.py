"""Command-line entry points for the local validation workflow."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .aggregate import build_candidates
from .config import existing_api_url, existing_page_size, load_dotenv, user_hash_salt
from .database import DanmakuDatabase
from .existing_api import fetch_existing_index
from .exporter import read_json, write_json_atomic
from .import_jsonl import import_jsonl

LOGGER = logging.getLogger(__name__)
DEFAULT_DATABASE = Path("data/danmaku.db")
DEFAULT_EXISTING_INDEX = Path("data/existing_index.json")
DEFAULT_CANDIDATES = Path("data/candidates.json")
DEFAULT_LIVE_JSONL = Path("data/live.jsonl")
DEFAULT_IMPORT_CHECKPOINT = Path("data/live.import.checkpoint.json")


def path_argument(value: str) -> Path:
    return Path(value)


def add_common_room(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--room-id", type=int, default=6657)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Douyu danmaku meme candidate finder")
    subparsers = parser.add_subparsers(dest="command", required=True)

    importer = subparsers.add_parser("import-jsonl", help="Import Node collector JSONL into SQLite")
    importer.add_argument("--input", type=path_argument, default=DEFAULT_LIVE_JSONL)
    importer.add_argument("--checkpoint", type=path_argument, default=DEFAULT_IMPORT_CHECKPOINT)
    importer.add_argument("--database", type=path_argument, default=DEFAULT_DATABASE)
    importer.add_argument("--batch-size", type=int, default=100)

    sync = subparsers.add_parser("sync-existing", help="Sync the existing public meme index")
    sync.add_argument("--output", type=path_argument, default=DEFAULT_EXISTING_INDEX)
    sync.add_argument("--page-size", type=int, default=None)
    sync.add_argument("--api-url", default=None)
    sync.add_argument("--retries", type=int, default=2)

    candidates = subparsers.add_parser("build-candidates", help="Build deterministic candidate JSON")
    add_common_room(candidates)
    candidates.add_argument("--window-hours", type=int, default=24)
    candidates.add_argument("--min-count", type=int, default=3)
    candidates.add_argument("--max-candidates", type=int, default=200)
    candidates.add_argument("--database", type=path_argument, default=DEFAULT_DATABASE)
    candidates.add_argument("--existing-index", type=path_argument, default=DEFAULT_EXISTING_INDEX)
    candidates.add_argument("--output", type=path_argument, default=DEFAULT_CANDIDATES)
    candidates.add_argument(
        "--similarity-threshold",
        type=float,
        default=None,
        help="Optionally merge obvious lexical variants (0.5 to 1.0; try 0.88)",
    )

    stats = subparsers.add_parser("stats", help="Show local collection statistics")
    add_common_room(stats)
    stats.add_argument("--database", type=path_argument, default=DEFAULT_DATABASE)
    stats.add_argument("--existing-index", type=path_argument, default=DEFAULT_EXISTING_INDEX)
    stats.add_argument("--candidates", type=path_argument, default=DEFAULT_CANDIDATES)
    return parser


async def _run_sync(args: argparse.Namespace) -> None:
    page_size = args.page_size if args.page_size is not None else existing_page_size()
    if page_size <= 0:
        raise ValueError("--page-size must be positive")
    payload = await fetch_existing_index(args.api_url or existing_api_url(), page_size, args.retries)
    write_json_atomic(args.output, payload)
    print(f"Synced {payload['total']} records ({len(payload['items'])} normalized entries) to {args.output}")


def _run_candidates(args: argparse.Namespace) -> None:
    if args.window_hours <= 0 or args.min_count < 1 or args.max_candidates < 0:
        raise ValueError("window hours and min count must be positive; max candidates cannot be negative")
    if args.similarity_threshold is not None and not 0.5 <= args.similarity_threshold <= 1.0:
        raise ValueError("--similarity-threshold must be between 0.5 and 1.0")
    with DanmakuDatabase(args.database) as database:
        payload = build_candidates(
            database,
            args.room_id,
            args.window_hours,
            args.min_count,
            args.max_candidates,
            args.existing_index,
            args.similarity_threshold,
        )
    write_json_atomic(args.output, payload)
    print(f"Wrote {len(payload['candidates'])} candidates to {args.output}")


def _run_import_jsonl(args: argparse.Namespace) -> None:
    with DanmakuDatabase(args.database) as database:
        result = import_jsonl(args.input, args.checkpoint, database, user_hash_salt(), args.batch_size)
    print(
        f"Imported {result['imported']} records, skipped {result['skipped']}; "
        f"checkpoint offset={result['offset']}"
    )


def _run_stats(args: argparse.Namespace) -> None:
    with DanmakuDatabase(args.database) as database:
        values = database.stats(args.room_id)
    existing = read_json(args.existing_index, {"items": {}}).get("items", {})
    candidates = read_json(args.candidates, {"candidates": []}).get("candidates", [])
    print(f"Database messages: {values['total']}")
    print(f"Last 24h messages: {values['recent']}")
    print(f"Last 24h unique texts: {values['unique']}")
    print(f"Latest danmaku: {values['last'] or 'none'}")
    print(f"Existing indexed memes: {len(existing) if isinstance(existing, dict) else 0}")
    print(f"Current candidates: {len(candidates) if isinstance(candidates, list) else 0}")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = create_parser().parse_args(argv)
    try:
        if args.command == "sync-existing":
            import asyncio

            asyncio.run(_run_sync(args))
        elif args.command == "import-jsonl":
            _run_import_jsonl(args)
        elif args.command == "build-candidates":
            _run_candidates(args)
        elif args.command == "stats":
            _run_stats(args)
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
