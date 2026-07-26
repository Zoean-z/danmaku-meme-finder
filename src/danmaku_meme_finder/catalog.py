"""Build the public GitHub catalog from legacy and local meme sources."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .database import iso_now
from .exporter import read_json, write_json_atomic
from .normalize import normalize_text

MAX_CATALOG_ID = 99_999
ACTIVE_MONTH_COUNT = 3
DATE_FIELDS = ("submittedAt", "addedAt", "firstSeenAt", "lastSeenAt")


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


def next_catalog_number(
    catalog: dict[str, Any], existing_index: dict[str, Any], memes: dict[str, Any] | None = None
) -> int:
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
    local_items = (memes or {}).get("memes", [])
    if isinstance(local_items, list):
        for item in local_items:
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
            for field in ("addedAt", "firstSeenAt", "lastSeenAt"):
                if raw.get(field) is not None:
                    source[field] = raw[field]
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


def _item_month(item: dict[str, Any]) -> str:
    dates = [
        value[:7]
        for source in item.get("sources", [])
        if isinstance(source, dict)
        for field in DATE_FIELDS
        if isinstance((value := source.get(field)), str) and len(value) >= 7
    ]
    return max(dates, default="undated")


def _previous_month(month: str) -> str:
    year, number = (int(part) for part in month.split("-", 1))
    return f"{year - 1}-12" if number == 1 else f"{year}-{number - 1:02d}"


def _active_months(latest_month: str, count: int) -> list[str]:
    months = [latest_month]
    while len(months) < count:
        months.append(_previous_month(months[-1]))
    return sorted(months)


def split_catalog(catalog: dict[str, Any], active_month_count: int = ACTIVE_MONTH_COUNT) -> dict[str, Any]:
    """Split a canonical catalog into one active set and immutable month shards."""
    items = catalog.get("items", [])
    if not isinstance(items, list):
        raise ValueError("catalog items must be a list")
    valid_items = [item for item in items if isinstance(item, dict)]
    dated_months = sorted({_item_month(item) for item in valid_items} - {"undated"})
    latest_month = dated_months[-1] if dated_months else iso_now().strftime("%Y-%m")
    active_months = _active_months(latest_month, active_month_count)
    active_set = set(active_months)
    active_items: list[dict[str, Any]] = []
    archives: dict[str, list[dict[str, Any]]] = {}
    for item in valid_items:
        month = _item_month(item)
        if month in active_set:
            active_items.append(item)
        else:
            archives.setdefault(month, []).append(item)

    generated_at = catalog.get("generatedAt") or iso_now().isoformat()
    room_id = int(catalog.get("roomId", 6657))
    active = {
        "schemaVersion": 2,
        "generatedAt": generated_at,
        "roomId": room_id,
        "months": active_months,
        "total": len(active_items),
        "items": active_items,
    }
    archive_documents = {
        month: {
            "schemaVersion": 2,
            "generatedAt": generated_at,
            "roomId": room_id,
            "month": month,
            "total": len(month_items),
            "items": month_items,
        }
        for month, month_items in sorted(archives.items(), reverse=True)
    }
    manifest = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "roomId": room_id,
        "total": len(valid_items),
        "active": {
            "file": "catalog/active.json",
            "months": active_months,
            "count": len(active_items),
        },
        "archives": [
            {
                "month": month,
                "file": f"catalog/archive/{month}.json",
                "count": len(document["items"]),
            }
            for month, document in archive_documents.items()
        ],
    }
    return {"manifest": manifest, "active": active, "archives": archive_documents}


def build_daily_trends(catalog: dict[str, Any]) -> dict[str, Any]:
    """Precompute historical totals so charts do not need old item shards."""
    raw_items = catalog.get("items", [])
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
    points: dict[str, dict[str, Any]] = {}
    for item in items:
        occurrences: Counter[str] = Counter()
        sources = item.get("sources", [])
        if isinstance(sources, list):
            for source in sources:
                if not isinstance(source, dict):
                    continue
                dates = [
                    value[:10]
                    for field in DATE_FIELDS
                    if isinstance((value := source.get(field)), str) and len(value) >= 10
                ]
                if dates:
                    occurrences[max(dates)] += int(source.get("count", 1) or 1)
        tags = _tags(item.get("tags"))
        identifier = str(item.get("id", item.get("key", "")))
        for date, count in occurrences.items():
            point = points.setdefault(
                date,
                {"barrageCount": 0, "memeIds": set(), "tagCounts": Counter()},
            )
            point["barrageCount"] += count
            point["memeIds"].add(identifier)
            point["tagCounts"].update(tags)

    return {
        "schemaVersion": 1,
        "generatedAt": catalog.get("generatedAt") or iso_now().isoformat(),
        "points": [
            {
                "date": date,
                "memeCount": len(point["memeIds"]),
                "barrageCount": point["barrageCount"],
                "tagCounts": dict(sorted(point["tagCounts"].items())),
            }
            for date, point in sorted(points.items())
        ],
    }


def load_distributed_catalog(directory: Path) -> dict[str, Any]:
    """Load only local generated shards for ID preservation during rebuilds."""
    items: list[dict[str, Any]] = []
    active = read_json(directory / "active.json", {"items": []}).get("items", [])
    if isinstance(active, list):
        items.extend(item for item in active if isinstance(item, dict))
    archive_dir = directory / "archive"
    if archive_dir.is_dir():
        for path in sorted(archive_dir.glob("*.json")):
            archive_items = read_json(path, {"items": []}).get("items", [])
            if isinstance(archive_items, list):
                items.extend(item for item in archive_items if isinstance(item, dict))
    return {"items": items}


def write_distributed_catalog(
    catalog: dict[str, Any], directory: Path, trends_path: Path
) -> dict[str, Any]:
    """Write all shards first and the manifest last, then remove stale shards."""
    split = split_catalog(catalog)
    archive_dir = directory / "archive"
    write_json_atomic(directory / "active.json", split["active"])
    expected: set[Path] = set()
    for month, document in split["archives"].items():
        path = archive_dir / f"{month}.json"
        write_json_atomic(path, document)
        expected.add(path.resolve())
    if archive_dir.is_dir():
        for path in archive_dir.glob("*.json"):
            if path.resolve() not in expected:
                path.unlink()
    write_json_atomic(trends_path, build_daily_trends(catalog))
    write_json_atomic(directory / "manifest.json", split["manifest"])
    return split["manifest"]
