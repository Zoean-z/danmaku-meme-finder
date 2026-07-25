"""Small local helpers for approving candidate memes with manual tags."""

from __future__ import annotations

from typing import Any

from .database import iso_now
from .normalize import normalize_text


def parse_tags(value: str) -> list[str]:
    """Parse the comma-separated tag IDs entered by a reviewer."""
    return sorted({part.strip() for part in value.split(",") if part.strip()})


def add_confirmed_meme(
    memes: dict[str, Any],
    candidate: dict[str, Any],
    tags: list[str],
    catalog_id: str,
) -> tuple[dict[str, Any], bool]:
    """Add a candidate once, or merge tags if it was already confirmed."""
    text = candidate.get("text")
    normalized = candidate.get("normalizedText")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("candidate text is missing")
    if not isinstance(normalized, str) or not normalized:
        normalized = normalize_text(text)
    if not normalized:
        raise ValueError("candidate text normalizes to empty")

    records = memes.setdefault("memes", [])
    if not isinstance(records, list):
        raise ValueError("memes must be a list")
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("text"), str):
            continue
        if normalize_text(record["text"]) == normalized:
            record["tags"] = sorted(set(parse_tags(",".join(record.get("tags", [])))) | set(tags))
            memes["updatedAt"] = iso_now().isoformat()
            return memes, False

    records.append({
        "id": catalog_id,
        "text": text,
        "tags": tags,
        "addedAt": iso_now().isoformat(),
    })
    memes["updatedAt"] = iso_now().isoformat()
    return memes, True
