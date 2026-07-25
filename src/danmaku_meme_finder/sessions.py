"""Public live-session snapshots and best-effort Douyu room metadata."""

from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any

import httpx

from .database import SHANGHAI, iso_now

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
        "roomId": room_id,
        "rid": metadata.get("rid"),
        "title": metadata.get("title"),
        "category": metadata.get("category"),
        "coverUrl": metadata.get("coverUrl"),
        "sourceUrl": metadata.get("sourceUrl", ROOM_PAGE_URL.format(room_id=room_id)),
        "observedStartedAt": started.isoformat(),
        "observedEndedAt": None,
        "metadataFetchedAt": iso_now().isoformat(),
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
            record["messageCount"] = message_count
            payload["updatedAt"] = iso_now().isoformat()
            return
    raise ValueError(f"unknown session ID: {identifier}")
