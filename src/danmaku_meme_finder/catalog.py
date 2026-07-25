"""Build the public GitHub catalog from legacy and local meme sources."""

from __future__ import annotations

from typing import Any

from .database import iso_now
from .normalize import normalize_text

MAX_CATALOG_ID = 99_999


def _tags(value: object) -> list[str]:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        return []
    return sorted({str(tag).strip() for tag in values if str(tag).strip()})


def catalog_number(value: object) -> int | None:
    """Return a valid five-digit catalog number, if *value* represents one."""
    if isinstance(value, bool):
        return None
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    return number if 0 < number <= MAX_CATALOG_ID else None


def format_catalog_id(number: int) -> str:
    if not 0 < number <= MAX_CATALOG_ID:
        raise ValueError(f"catalog ID must be between 00001 and {MAX_CATALOG_ID:05d}")
    return f"{number:05d}"


def next_catalog_number(catalog: dict[str, Any], existing_index: dict[str, Any]) -> int:
    """Find the next unused display ID from the current public/local sources."""
    used: set[int] = set()
    items = catalog.get("items", [])
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                number = catalog_number(item.get("id"))
                if number is not None:
                    used.add(number)
    legacy_items = existing_index.get("items", {})
    if isinstance(legacy_items, dict):
        for item in legacy_items.values():
            if isinstance(item, dict):
                number = catalog_number(item.get("id"))
                if number is not None:
                    used.add(number)
    candidate = max(used, default=0) + 1
    if candidate > MAX_CATALOG_ID:
        raise ValueError("no five-digit catalog IDs remain")
    return candidate


def _previous_ids(catalog: dict[str, Any]) -> tuple[dict[str, int], set[int]]:
    by_key: dict[str, int] = {}
    used: set[int] = set()
    items = catalog.get("items", [])
    if not isinstance(items, list):
        return by_key, used
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        number = catalog_number(item.get("id"))
        if isinstance(key, str) and key and number is not None and number not in used:
            by_key[key] = number
            used.add(number)
    return by_key, used


def _assign_ids(merged: dict[str, dict[str, Any]], previous_catalog: dict[str, Any]) -> None:
    """Keep previous IDs, prefer legacy source IDs, then allocate sequentially."""
    previous_by_key, used = _previous_ids(previous_catalog)
    pending: list[tuple[str, dict[str, Any]]] = []

    for key in sorted(merged):
        entry = merged[key]
        previous = previous_by_key.get(key)
        if previous is not None:
            entry["id"] = format_catalog_id(previous)
            continue
        preferred: int | None = None
        for source in entry["sources"]:
            if source.get("kind") == "legacy_api":
                preferred = catalog_number(source.get("sourceId"))
                if preferred is not None:
                    break
        if preferred is None:
            for source in entry["sources"]:
                if source.get("kind") == "local":
                    preferred = catalog_number(source.get("sourceId"))
                    if preferred is not None:
                        break
        if preferred is not None and preferred not in used:
            entry["id"] = format_catalog_id(preferred)
            used.add(preferred)
        else:
            pending.append((key, entry))

    next_number = max(used, default=0) + 1
    for _, entry in pending:
        while next_number in used:
            next_number += 1
        if next_number > MAX_CATALOG_ID:
            raise ValueError("no five-digit catalog IDs remain")
        entry["id"] = format_catalog_id(next_number)
        used.add(next_number)
        next_number += 1


def build_catalog(
    existing_index: dict[str, Any],
    memes: dict[str, Any],
    room_id: int,
    previous_catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge by normalized text while retaining each source's own metadata."""
    merged: dict[str, dict[str, Any]] = {}
    legacy_items = existing_index.get("items", {})
    if isinstance(legacy_items, dict):
        for key, raw in legacy_items.items():
            if not isinstance(raw, dict):
                continue
            normalized = str(key)
            text = raw.get("barrage")
            if not normalized or not isinstance(text, str) or not text:
                continue
            merged[normalized] = {
                "key": normalized,
                "text": text,
                "tags": _tags(raw.get("tags")),
                "sources": [{
                    "kind": "legacy_api",
                    "sourceId": str(raw.get("id")),
                    "count": int(raw.get("cnt", 0) or 0),
                    "submittedAt": raw.get("submitTime"),
                }],
            }

    local_records = memes.get("memes", [])
    local_count = 0
    if isinstance(local_records, list):
        for raw in local_records:
            if not isinstance(raw, dict):
                continue
            text = raw.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            normalized = normalize_text(text)
            if not normalized:
                continue
            local_count += 1
            entry = merged.setdefault(normalized, {
                "key": normalized,
                "text": text,
                "tags": [],
                "sources": [],
            })
            entry["tags"] = sorted(set(entry["tags"]) | set(_tags(raw.get("tags"))))
            source: dict[str, Any] = {"kind": "local"}
            if raw.get("id") is not None:
                source["sourceId"] = str(raw["id"])
            if raw.get("addedAt") is not None:
                source["addedAt"] = raw["addedAt"]
            entry["sources"].append(source)

    _assign_ids(merged, previous_catalog or {})
    items = [merged[key] for key in sorted(merged)]
    return {
        "schemaVersion": 2,
        "generatedAt": iso_now().isoformat(),
        "roomId": room_id,
        "summary": {
            "legacyRecords": int(existing_index.get("total", 0) or 0),
            "legacyUniqueTexts": len(legacy_items) if isinstance(legacy_items, dict) else 0,
            "localRecords": local_count,
            "mergedItems": len(items),
        },
        "items": items,
    }
