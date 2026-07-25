"""Simple deterministic rules for candidate-meme selection."""

from __future__ import annotations

from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .database import DanmakuDatabase, iso_now
from .exporter import read_json
from .normalize import has_meaningful_content


def _near_duplicate(left: str, right: str, threshold: float) -> bool:
    """Return whether two normalized texts are obvious textual variants.

    This is intentionally lexical, not semantic: it collapses copied text,
    small edits, and a short phrase embedded in a longer repeated version.
    """
    left_compact = "".join(character for character in left if character.isalnum())
    right_compact = "".join(character for character in right if character.isalnum())
    if left_compact == right_compact:
        return True
    if min(len(left_compact), len(right_compact)) < 8:
        return False
    if left_compact in right_compact or right_compact in left_compact:
        return True
    return SequenceMatcher(None, left_compact, right_compact, autojunk=False).ratio() >= threshold


def deduplicate_similar_candidates(
    candidates: list[dict[str, Any]], threshold: float
) -> tuple[list[dict[str, Any]], int]:
    """Keep the first ranked representative and attach its close variants."""
    if not 0.5 <= threshold <= 1.0:
        raise ValueError("similarity threshold must be between 0.5 and 1.0")

    representatives: list[dict[str, Any]] = []
    merged = 0
    for candidate in candidates:
        normalized = str(candidate["normalizedText"])
        for representative in representatives:
            if _near_duplicate(normalized, str(representative["normalizedText"]), threshold):
                variants = representative.setdefault("similarVariants", [])
                variants.append({
                    "text": candidate["text"],
                    "normalizedText": normalized,
                    "count": candidate["count"],
                    "uniqueUsers": candidate["uniqueUsers"],
                })
                merged += 1
                break
        else:
            representatives.append(dict(candidate))
    return representatives, merged


def build_candidates(
    database: DanmakuDatabase,
    room_id: int,
    window_hours: int,
    min_count: int,
    max_candidates: int,
    existing_index_path: Path,
    similarity_threshold: float | None = None,
) -> dict[str, Any]:
    end = iso_now()
    start = end - timedelta(hours=window_hours)
    raw_count, rows = database.aggregate_since(room_id, start)
    index = read_json(existing_index_path, {"items": {}})
    existing = index.get("items", {})
    existing_keys = set(existing) if isinstance(existing, dict) else set()
    existing_filtered = 0
    candidates: list[dict[str, Any]] = []

    for row in rows:
        normalized = str(row["normalized_content"])
        count = int(row["count"])
        if normalized in existing_keys:
            existing_filtered += 1
            continue
        if len(normalized) < 2 or not has_meaningful_content(normalized):
            continue
        source: str | None = "high_frequency" if count >= min_count else None
        if source is None and count == 1 and len(normalized) >= 20:
            source = "long_text"
        if source is None:
            continue
        candidates.append({
            "text": row["text"], "normalizedText": normalized, "count": count,
            "uniqueUsers": int(row["unique_users"]), "firstSeenAt": row["first_seen_at"],
            "lastSeenAt": row["last_seen_at"], "source": source,
        })

    # Stable tiebreakers keep unchanged inputs from generating meaningless Git diffs.
    candidates.sort(key=lambda item: (
        -int(item["count"]), -int(item["uniqueUsers"]),
        -datetime.fromisoformat(str(item["lastSeenAt"])).timestamp(),
        abs(len(str(item["normalizedText"])) - 12), str(item["normalizedText"]),
    ))
    result: dict[str, Any] = {
        "roomId": room_id, "windowStart": start.isoformat(), "windowEnd": end.isoformat(),
        "generatedAt": iso_now().isoformat(), "totalRawMessages": raw_count,
        "totalUniqueMessages": len(rows), "existingFilteredCount": existing_filtered,
    }
    if similarity_threshold is not None:
        candidates, merged = deduplicate_similar_candidates(candidates, similarity_threshold)
        result["similarityDeduplication"] = {
            "threshold": similarity_threshold,
            "mergedCandidates": merged,
        }
    result["candidates"] = candidates[:max(0, max_candidates)]
    return result
