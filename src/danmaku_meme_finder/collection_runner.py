"""Orchestrate Node collection with local SQLite and candidate processing."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .aggregate import DEFAULT_SIMILARITY_THRESHOLD, build_candidates
from .database import DanmakuDatabase
from .exporter import read_json, write_json_atomic
from .import_jsonl import import_jsonl
from .sessions import begin_session, fetch_room_metadata, finish_session

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CollectionSettings:
    room_id: int
    database_path: Path
    input_path: Path
    checkpoint_path: Path
    existing_index_path: Path
    output_path: Path
    memes_path: Path = Path("data/memes.json")
    sessions_path: Path = Path("data/sessions.json")
    review_state_path: Path = Path("data/review_state.json")
    flush_interval: float = 5.0
    batch_size: int = 100
    window_hours: int = 24
    min_count: int = 3
    max_candidates: int = 20
    similarity_threshold: float | None = DEFAULT_SIMILARITY_THRESHOLD
    duration_seconds: int | None = None


def import_pending(settings: CollectionSettings, salt: str) -> dict[str, int]:
    """Commit complete newly appended JSONL lines to SQLite."""
    with DanmakuDatabase(settings.database_path) as database:
        return import_jsonl(
            settings.input_path,
            settings.checkpoint_path,
            database,
            salt,
            settings.batch_size,
        )


def build_current_candidates(settings: CollectionSettings) -> dict[str, Any]:
    """Build the review output after the final SQLite flush."""
    with DanmakuDatabase(settings.database_path) as database:
        payload = build_candidates(
            database,
            settings.room_id,
            settings.window_hours,
            settings.min_count,
            settings.max_candidates,
            settings.existing_index_path,
            settings.similarity_threshold,
            settings.memes_path,
            settings.review_state_path,
        )
    write_json_atomic(settings.output_path, payload)
    return payload


async def run_collection(settings: CollectionSettings, salt: str, project_root: Path) -> dict[str, Any]:
    """Run Node collection until interrupted, then flush and write candidates."""
    if settings.flush_interval <= 0:
        raise ValueError("flush interval must be positive")

    environment = os.environ.copy()
    environment["ROOM_ID"] = str(settings.room_id)
    environment["LIVE_JSONL_PATH"] = str(settings.input_path.resolve())
    if settings.duration_seconds is not None:
        environment["COLLECTOR_MAX_SECONDS"] = str(settings.duration_seconds)

    try:
        metadata = await fetch_room_metadata(settings.room_id)
    except (httpx.HTTPError, OSError, ValueError) as exc:
        LOGGER.warning("Could not fetch room metadata: %s", exc)
        metadata = {"roomId": settings.room_id, "sourceUrl": f"https://www.douyu.com/{settings.room_id}"}
    sessions = read_json(settings.sessions_path, {"schemaVersion": 1, "sessions": []})
    session = begin_session(sessions, settings.room_id, metadata)
    write_json_atomic(settings.sessions_path, sessions)
    environment["SESSION_ID"] = str(session["id"])

    supervisor = project_root / "collector-js" / "run-collector.js"
    process = await asyncio.create_subprocess_exec(
        "node", str(supervisor), cwd=str(project_root), env=environment
    )
    LOGGER.info("Started Node collector pid=%s for room %s", process.pid, settings.room_id)
    final_import: dict[str, int] = {"imported": 0, "skipped": 0, "offset": 0}
    try:
        while process.returncode is None:
            await asyncio.sleep(settings.flush_interval)
            result = import_pending(settings, salt)
            if result["imported"] or result["skipped"]:
                LOGGER.info(
                    "Imported %s messages (skipped %s); checkpoint=%s",
                    result["imported"], result["skipped"], result["offset"],
                )
        await process.wait()
        if process.returncode:
            LOGGER.warning("Node collector supervisor exited with code %s", process.returncode)
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()
        final_import = import_pending(settings, salt)
        candidates = build_current_candidates(settings)
        with DanmakuDatabase(settings.database_path) as database:
            message_count = database.session_message_count(str(session["id"]))
        finish_session(sessions, str(session["id"]), message_count)
        write_json_atomic(settings.sessions_path, sessions)
        LOGGER.info(
            "Final import=%s; wrote %s candidates to %s",
            final_import["imported"], len(candidates["candidates"]), settings.output_path,
        )
    return {"import": final_import, "candidates": candidates, "session": session}
