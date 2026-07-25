"""Small local helpers for approving candidate memes with manual tags."""

from __future__ import annotations

from typing import Any

from .database import iso_now
from .normalize import normalize_text


def parse_tags(value: str) -> list[str]:
    """Parse the comma-separated tag IDs entered by a reviewer."""
    return sorted({part.strip() for part in value.replace("，", ",").split(",") if part.strip()})


def tag_labels(payload: dict[str, Any]) -> dict[str, str]:
    """Read the small public tag catalog into code-to-label form."""
    raw_tags = payload.get("tags", {})
    if not isinstance(raw_tags, dict):
        raise ValueError("tag catalog tags must be an object")
    labels: dict[str, str] = {}
    for code, raw in raw_tags.items():
        if not isinstance(code, str):
            continue
        label = raw.get("label") if isinstance(raw, dict) else raw
        if isinstance(label, str) and label.strip():
            labels[code] = label.strip()
    return labels


def resolve_tags(value: str, labels: dict[str, str]) -> list[str]:
    """Accept either a tag code or its human-readable label."""
    by_label = {label.casefold(): code for code, label in labels.items()}
    resolved: set[str] = set()
    for token in parse_tags(value):
        code = token if token in labels else by_label.get(token.casefold())
        if code is None:
            raise ValueError(f"unknown tag: {token}; enter ? to list available tags")
        resolved.add(code)
    return sorted(resolved)


def format_tag_catalog(labels: dict[str, str]) -> str:
    """Make a compact terminal-readable tag menu."""
    return "\n".join(f"{code}: {labels[code]}" for code in sorted(labels))


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

    record: dict[str, Any] = {
        "id": catalog_id,
        "text": text,
        "tags": tags,
        "addedAt": iso_now().isoformat(),
    }
    for field in ("firstSeenAt", "lastSeenAt"):
        value = candidate.get(field)
        if isinstance(value, str) and value:
            record[field] = value
    records.append(record)
    memes["updatedAt"] = iso_now().isoformat()
    return memes, True
