"""Build the public GitHub catalog from legacy and local meme sources."""

from __future__ import annotations

import hashlib
from typing import Any

from .database import iso_now
from .normalize import normalize_text


def _tags(value: object) -> list[str]:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        return []
    return sorted({str(tag).strip() for tag in values if str(tag).strip()})


def catalog_id(normalized_text: str) -> str:
    """Return a stable public ID independent of either source's numeric IDs."""
    digest = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:20]
    return f"m_{digest}"


def build_catalog(existing_index: dict[str, Any], memes: dict[str, Any], room_id: int) -> dict[str, Any]:
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
                "id": catalog_id(normalized),
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
                "id": catalog_id(normalized),
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

    items = [merged[key] for key in sorted(merged)]
    return {
        "schemaVersion": 1,
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
