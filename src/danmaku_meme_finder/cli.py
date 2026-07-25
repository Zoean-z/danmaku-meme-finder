"""Command-line entry points for the local validation workflow."""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from .aggregate import build_candidates
from .catalog import build_catalog, format_catalog_id, next_catalog_number
from .collection_runner import CollectionSettings, run_collection
from .config import existing_api_url, existing_page_size, load_dotenv, user_hash_salt
from .database import DanmakuDatabase
from .curation import add_confirmed_meme, parse_tags
from .existing_api import fetch_existing_index
from .exporter import read_json, write_json_atomic
from .import_jsonl import import_jsonl

LOGGER = logging.getLogger(__name__)
DEFAULT_DATABASE = Path("data/danmaku.db")
DEFAULT_EXISTING_INDEX = Path("data/existing_index.json")
DEFAULT_CANDIDATES = Path("data/candidates.json")
DEFAULT_CATALOG = Path("data/catalog.json")
DEFAULT_SESSIONS = Path("data/sessions.json")
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

    catalog = subparsers.add_parser("build-catalog", help="Merge legacy and local memes for static GitHub reads")
    add_common_room(catalog)
    catalog.add_argument("--existing-index", type=path_argument, default=DEFAULT_EXISTING_INDEX)
    catalog.add_argument("--memes", type=path_argument, default=Path("data/memes.json"))
    catalog.add_argument("--output", type=path_argument, default=DEFAULT_CATALOG)

    review = subparsers.add_parser("review-candidates", help="Interactively confirm candidates and enter tag IDs")
    review.add_argument("--candidates", type=path_argument, default=DEFAULT_CANDIDATES)
    review.add_argument("--memes", type=path_argument, default=Path("data/memes.json"))
    review.add_argument("--existing-index", type=path_argument, default=DEFAULT_EXISTING_INDEX)
    review.add_argument("--catalog", type=path_argument, default=DEFAULT_CATALOG)
    add_common_room(review)

    collect = subparsers.add_parser("collect", help="Run Node collection with periodic SQLite import")
    add_common_room(collect)
    collect.add_argument("--database", type=path_argument, default=DEFAULT_DATABASE)
    collect.add_argument("--input", type=path_argument, default=DEFAULT_LIVE_JSONL)
    collect.add_argument("--checkpoint", type=path_argument, default=DEFAULT_IMPORT_CHECKPOINT)
    collect.add_argument("--existing-index", type=path_argument, default=DEFAULT_EXISTING_INDEX)
    collect.add_argument("--output", type=path_argument, default=DEFAULT_CANDIDATES)
    collect.add_argument("--sessions", type=path_argument, default=DEFAULT_SESSIONS)
    collect.add_argument("--flush-interval", type=float, default=5.0)
    collect.add_argument("--batch-size", type=int, default=100)
    collect.add_argument("--window-hours", type=int, default=24)
    collect.add_argument("--min-count", type=int, default=3)
    collect.add_argument("--max-candidates", type=int, default=200)
    collect.add_argument("--similarity-threshold", type=float, default=0.88)
    collect.add_argument("--duration", type=int, default=None, help="Optional automatic stop time in seconds")
    collect.add_argument("--refresh-existing", action="store_true", help="Refresh the external meme index first")

    stats = subparsers.add_parser("stats", help="Show local collection statistics")
    add_common_room(stats)
    stats.add_argument("--database", type=path_argument, default=DEFAULT_DATABASE)
    stats.add_argument("--existing-index", type=path_argument, default=DEFAULT_EXISTING_INDEX)
    stats.add_argument("--candidates", type=path_argument, default=DEFAULT_CANDIDATES)

    backfill = subparsers.add_parser("backfill-sessions", help="Associate stored historical messages with session JSON")
    backfill.add_argument("--database", type=path_argument, default=DEFAULT_DATABASE)
    backfill.add_argument("--sessions", type=path_argument, default=DEFAULT_SESSIONS)
    return parser


async def _run_sync(args: argparse.Namespace) -> None:
    page_size = args.page_size if args.page_size is not None else existing_page_size()
    await _sync_existing(args.output, args.api_url, page_size, args.retries)


async def _sync_existing(output: Path, api_url: str | None, page_size: int, retries: int) -> None:
    if page_size <= 0:
        raise ValueError("--page-size must be positive")
    payload = await fetch_existing_index(api_url or existing_api_url(), page_size, retries)
    write_json_atomic(output, payload)
    print(f"Synced {payload['total']} records ({len(payload['items'])} normalized entries) to {output}")


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


def _run_catalog(args: argparse.Namespace) -> None:
    existing_index = read_json(args.existing_index, {"items": {}, "total": 0})
    memes = read_json(args.memes, {"memes": []})
    previous_catalog = read_json(args.output, {"items": []})
    payload = build_catalog(existing_index, memes, args.room_id, previous_catalog)
    write_json_atomic(args.output, payload)
    print(f"Wrote {payload['summary']['mergedItems']} catalog items to {args.output}")


def _run_review_candidates(args: argparse.Namespace) -> None:
    candidates = read_json(args.candidates, {"candidates": []}).get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")
    memes = read_json(args.memes, {"roomId": args.room_id, "memes": []})
    memes.setdefault("roomId", args.room_id)
    existing_index = read_json(args.existing_index, {"items": {}})
    catalog = read_json(args.catalog, {"items": []})
    next_number = next_catalog_number(catalog, existing_index)
    added = 0
    changed = False

    for index, candidate in enumerate(candidates, start=1):
        if not isinstance(candidate, dict):
            continue
        text = candidate.get("text", "")
        print(f"\n[{index}/{len(candidates)}] {text}")
        print(
            f"count={candidate.get('count', 0)} users={candidate.get('uniqueUsers', 0)} "
            f"source={candidate.get('source', 'unknown')}"
        )
        answer = input("输入标签编号（如 06,24）；回车跳过；q 结束：").strip()
        if answer.lower() == "q":
            break
        tags = parse_tags(answer)
        if not tags:
            continue
        catalog_id = format_catalog_id(next_number)
        memes, created = add_confirmed_meme(memes, candidate, tags, catalog_id)
        write_json_atomic(args.memes, memes)
        changed = True
        if created:
            added += 1
            next_number += 1
            print(f"已收录为 #{catalog_id}")
        else:
            print("已存在，已合并标签")

    if changed:
        payload = build_catalog(existing_index, memes, args.room_id, catalog)
        write_json_atomic(args.catalog, payload)
        print(f"已更新 {args.memes} 和 {args.catalog}，新增 {added} 条。")
    else:
        print("没有新增正式梗。")


async def _run_collect(args: argparse.Namespace) -> None:
    if args.refresh_existing or not args.existing_index.is_file():
        await _sync_existing(args.existing_index, None, existing_page_size(), 2)
    if args.flush_interval <= 0 or args.batch_size <= 0 or args.window_hours <= 0:
        raise ValueError("flush interval, batch size, and window hours must be positive")
    if args.min_count < 1 or args.max_candidates < 0:
        raise ValueError("min count must be positive; max candidates cannot be negative")
    if not 0.5 <= args.similarity_threshold <= 1.0:
        raise ValueError("--similarity-threshold must be between 0.5 and 1.0")
    if args.duration is not None and args.duration <= 0:
        raise ValueError("--duration must be positive")

    settings = CollectionSettings(
        room_id=args.room_id,
        database_path=args.database,
        input_path=args.input,
        checkpoint_path=args.checkpoint,
        existing_index_path=args.existing_index,
        output_path=args.output,
        sessions_path=args.sessions,
        flush_interval=args.flush_interval,
        batch_size=args.batch_size,
        window_hours=args.window_hours,
        min_count=args.min_count,
        max_candidates=args.max_candidates,
        similarity_threshold=args.similarity_threshold,
        duration_seconds=args.duration,
    )
    result = await run_collection(settings, user_hash_salt(), Path.cwd())
    print(
        f"Stopped: final import={result['import']['imported']}; "
        f"candidates={len(result['candidates']['candidates'])}; session={result['session']['id']}; output={args.output}"
    )


def _run_backfill_sessions(args: argparse.Namespace) -> None:
    payload = read_json(args.sessions, {"sessions": []})
    sessions = payload.get("sessions", [])
    if not isinstance(sessions, list):
        raise ValueError("sessions must be a list")
    updated = 0
    with DanmakuDatabase(args.database) as database:
        for session in sessions:
            if not isinstance(session, dict):
                continue
            identifier = session.get("id")
            room_id = session.get("roomId")
            start = session.get("observedStartedAt")
            end = session.get("observedEndedAt")
            if not isinstance(identifier, str) or not isinstance(room_id, int) or not isinstance(start, str) or not isinstance(end, str):
                continue
            count = database.attach_session_for_range(
                identifier, room_id, datetime.fromisoformat(start), datetime.fromisoformat(end)
            )
            session["messageCount"] = database.session_message_count(identifier)
            updated += count
    write_json_atomic(args.sessions, payload)
    print(f"Associated {updated} historical messages with sessions in {args.sessions}")


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
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = create_parser().parse_args(argv)
    try:
        if args.command == "sync-existing":
            asyncio.run(_run_sync(args))
        elif args.command == "import-jsonl":
            _run_import_jsonl(args)
        elif args.command == "collect":
            asyncio.run(_run_collect(args))
        elif args.command == "build-catalog":
            _run_catalog(args)
        elif args.command == "review-candidates":
            _run_review_candidates(args)
        elif args.command == "build-candidates":
            _run_candidates(args)
        elif args.command == "stats":
            _run_stats(args)
        elif args.command == "backfill-sessions":
            _run_backfill_sessions(args)
        return 0
    except KeyboardInterrupt:
        LOGGER.info("Stopped by user")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
