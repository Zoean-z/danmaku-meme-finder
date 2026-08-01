"""Public live-session snapshots and best-effort Douyu room metadata."""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

import httpx

from .database import SHANGHAI, DanmakuDatabase, iso_now
from .normalize import normalize_text

ROOM_PAGE_URL = "https://www.douyu.com/{room_id}"
MOBILE_ROOM_URL = "https://m.douyu.com/{room_id}"


def _clean_html(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def _first(pattern: str, source: str) -> str | None:
    match = re.search(pattern, source, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else None


def parse_room_metadata(room_id: int, page_html: str, mobile_html: str = "") -> dict[str, Any]:
    """Extract only public room metadata; absent fields stay null."""
    title = _first(r"<h1[^>]*>(.*?)</h1>", page_html)
    if title is None:
        title = _first(r"<title[^>]*>(.*?)</title>", page_html)
    rid = _first(r'"rid"\s*:\s*(\d+)', mobile_html) or _first(r'"rid"\s*:\s*(\d+)', page_html)
    decoded = page_html.replace("\\u002F", "/").replace("\\/", "/")
    cover = _first(r"(https?://rpic\.douyucdn\.cn/[^\"'\s<>]+)", decoded)
    category = _first(r'<a[^>]+href="[^\"]*/g/[^\"]*"[^>]*>\s*([^<]+?)\s*</a>', page_html)
    if category is None:
        description = _first(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', page_html)
        if description:
            description_categories = re.findall(r"最精彩的([A-Za-z0-9]+)直播", html.unescape(description))
            category = description_categories[-1] if description_categories else None
    return {
        "roomId": room_id,
        "rid": int(rid) if rid is not None else None,
        "title": _clean_html(title) if title else None,
        "category": _clean_html(category) if category else None,
        "coverUrl": html.unescape(cover) if cover else None,
        "sourceUrl": ROOM_PAGE_URL.format(room_id=room_id),
    }


async def fetch_room_metadata(room_id: int) -> dict[str, Any]:
    """Fetch a best-effort public snapshot without blocking collection on failure."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; danmaku-meme-finder/0.1)"}
    timeout = httpx.Timeout(10.0, connect=5.0)
    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        page_response = await client.get(ROOM_PAGE_URL.format(room_id=room_id))
        page_response.raise_for_status()
        mobile_response = await client.get(MOBILE_ROOM_URL.format(room_id=room_id))
        mobile_response.raise_for_status()
    return parse_room_metadata(room_id, page_response.text, mobile_response.text)


def session_id(room_id: int, started_at: datetime) -> str:
    local = started_at.astimezone(SHANGHAI)
    return f"{room_id}-{local:%Y%m%d-%H%M%S}"


def begin_session(
    payload: dict[str, Any], room_id: int, metadata: dict[str, Any], started_at: datetime | None = None
) -> dict[str, Any]:
    """Append a local observation session to the public JSON payload."""
    started = (started_at or iso_now()).astimezone(SHANGHAI)
    record = {
        "id": session_id(room_id, started),
        "date": started.date().isoformat(),
        "roomId": room_id,
        "rid": metadata.get("rid"),
        "title": metadata.get("title"),
        "category": metadata.get("category"),
        "coverUrl": metadata.get("coverUrl"),
        "sourceUrl": metadata.get("sourceUrl", ROOM_PAGE_URL.format(room_id=room_id)),
        "observedStartedAt": started.isoformat(),
        "observedEndedAt": None,
        "metadataFetchedAt": iso_now().isoformat(),
        "summary": "",
        "memeCount": 0,
        "barrageCount": 0,
        "messageCount": 0,
    }
    sessions = payload.setdefault("sessions", [])
    if not isinstance(sessions, list):
        raise ValueError("sessions must be a list")
    sessions.append(record)
    payload["schemaVersion"] = 1
    payload["updatedAt"] = iso_now().isoformat()
    return record


def finish_session(payload: dict[str, Any], identifier: str, message_count: int, ended_at: datetime | None = None) -> None:
    sessions = payload.get("sessions", [])
    if not isinstance(sessions, list):
        raise ValueError("sessions must be a list")
    for record in sessions:
        if isinstance(record, dict) and record.get("id") == identifier:
            record["observedEndedAt"] = (ended_at or iso_now()).astimezone(SHANGHAI).isoformat()
            record["barrageCount"] = message_count
            record["messageCount"] = message_count
            payload["updatedAt"] = iso_now().isoformat()
            return
    raise ValueError(f"unknown session ID: {identifier}")


def refresh_session_provenance(
    sessions_payload: dict[str, Any],
    memes_payload: dict[str, Any],
    database: DanmakuDatabase | None,
    room_id: int,
) -> int:
    """Backfill exact meme occurrences and refresh public per-session totals."""
    memes = memes_payload.get("memes", [])
    sessions = sessions_payload.get("sessions", [])
    if not isinstance(memes, list) or not isinstance(sessions, list):
        raise ValueError("memes and sessions must be lists")

    database_occurrences: dict[str, list[dict[str, Any]]] = {}
    if database is not None:
        for row in database.session_occurrences(room_id):
            first_seen = str(row["first_seen_at"])
            database_occurrences.setdefault(str(row["normalized_content"]), []).append({
                "sessionId": str(row["session_id"]),
                "date": datetime.fromisoformat(first_seen).astimezone(SHANGHAI).date().isoformat(),
                "count": int(row["count"]),
                "firstSeenAt": first_seen,
                "lastSeenAt": str(row["last_seen_at"]),
            })

    updated = 0
    for meme in memes:
        if not isinstance(meme, dict) or not isinstance(meme.get("text"), str):
            continue
        occurrences = database_occurrences.get(normalize_text(meme["text"]))
        if occurrences and meme.get("collectionOccurrences") != occurrences:
            meme["collectionOccurrences"] = occurrences
            meme["firstSeenAt"] = min(item["firstSeenAt"] for item in occurrences)
            meme["lastSeenAt"] = max(item["lastSeenAt"] for item in occurrences)
            updated += 1

    meme_ids_by_session: dict[str, set[str]] = {}
    tag_counts_by_session: dict[str, dict[str, int]] = {}
    for index, meme in enumerate(memes):
        if not isinstance(meme, dict):
            continue
        identifier = str(meme.get("id", index))
        tags = [str(tag) for tag in meme.get("tags", [])] if isinstance(meme.get("tags"), list) else []
        occurrences = meme.get("collectionOccurrences", [])
        if not isinstance(occurrences, list):
            continue
        exact_occurrences = [
            occurrence
            for occurrence in occurrences
            if isinstance(occurrence, dict) and isinstance(occurrence.get("sessionId"), str)
        ]
        if not exact_occurrences:
            continue
        # A meme can recur in many later broadcasts. Session archives describe where
        # it first entered this collection, while the full occurrence list remains as
        # evidence and supplies the all-time heat count.
        occurrence = min(
            exact_occurrences,
            key=lambda item: (
                str(item.get("firstSeenAt") or item.get("date") or ""),
                str(item["sessionId"]),
            ),
        )
        session_identifier = str(occurrence["sessionId"])
        meme_ids_by_session.setdefault(session_identifier, set()).add(identifier)
        counts = tag_counts_by_session.setdefault(session_identifier, {})
        for tag in tags:
            counts[tag] = counts.get(tag, 0) + 1

    for session in sessions:
        if not isinstance(session, dict) or not isinstance(session.get("id"), str):
            continue
        identifier = session["id"]
        session["memeCount"] = len(meme_ids_by_session.get(identifier, set()))
        tag_counts = tag_counts_by_session.get(identifier, {})
        session["tagCodes"] = [
            code for code, _ in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
        ]
        if database is not None:
            message_count = database.session_message_count(identifier)
            if message_count > 0 or "messageCount" not in session:
                session["barrageCount"] = message_count
                session["messageCount"] = message_count

    now = iso_now().isoformat()
    sessions_payload["updatedAt"] = now
    if updated:
        memes_payload["updatedAt"] = now
    return updated
