"""Simple deterministic rules for candidate-meme selection."""

from __future__ import annotations

from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
import re
from typing import Any

from .database import SHANGHAI, DanmakuDatabase, iso_now
from .exporter import read_json
from .normalize import has_meaningful_content, normalize_text

MIN_CANDIDATE_LENGTH = 5
EXCLUDED_ACTIVITY_TEXTS = frozenset({"保卫鱼娘"})
DEFAULT_SIMILARITY_THRESHOLD = 0.82
_MENTION_TOKEN = re.compile(r"@[^\s:：@]{1,40}(?:[:：])?")
_CONTROL_PREFIXES = ("#显示", "#隐藏", "#关闭", "#开启")


def _local_meme_keys(memes_path: Path | None) -> set[str]:
    if memes_path is None:
        return set()
    payload = read_json(memes_path, {"memes": []})
    records = payload.get("memes", []) if isinstance(payload, dict) else []
    if not isinstance(records, list):
        return set()
    return {
        normalized
        for record in records
        if isinstance(record, dict)
        and isinstance(record.get("text"), str)
        and (normalized := normalize_text(record["text"]))
    }


def _rejected_keys(review_state_path: Path | None) -> set[str]:
    if review_state_path is None:
        return set()
    payload = read_json(review_state_path, {"rejected": {}})
    rejected = payload.get("rejected", {}) if isinstance(payload, dict) else {}
    return set(rejected) if isinstance(rejected, dict) else set()


def _comparison_text(text: str) -> str:
    text = _MENTION_TOKEN.sub("", text.casefold())
    compact = "".join(character for character in text if character.isalnum())
    while len(compact) > 6 and compact.endswith("喵"):
        compact = compact[:-1]
    return compact


def _reference_buckets(keys: set[str]) -> dict[str, set[str]]:
    buckets: dict[str, set[str]] = {}
    for key in keys:
        compact = _comparison_text(key)
        if len(compact) < 6:
            continue
        for token in (f"p:{compact[:4]}", f"s:{compact[-4:]}"):
            buckets.setdefault(token, set()).add(key)
    return buckets


def _near_reference(text: str, buckets: dict[str, set[str]], threshold: float) -> bool:
    compact = _comparison_text(text)
    if len(compact) < 6:
        return False
    references = buckets.get(f"p:{compact[:4]}", set()) | buckets.get(f"s:{compact[-4:]}", set())
    return any(_near_duplicate(text, reference, threshold) for reference in references)


def _is_activity_text(text: str) -> bool:
    compact = _comparison_text(text)
    return text.strip().startswith(_CONTROL_PREFIXES) or text in EXCLUDED_ACTIVITY_TEXTS or (
        compact.startswith("保卫") and "查看活动" in compact
    )


def _near_duplicate(left: str, right: str, threshold: float) -> bool:
    """Return whether two normalized texts are obvious textual variants.

    This is intentionally lexical, not semantic: it collapses copied text,
    small edits, and a short phrase embedded in a longer repeated version.
    """
    left_compact = _comparison_text(left)
    right_compact = _comparison_text(right)
    if left_compact == right_compact:
        return True
    shorter = min(len(left_compact), len(right_compact))
    longer = max(len(left_compact), len(right_compact))
    if shorter < 6:
        return False
    if shorter >= 8 and shorter / longer >= 0.35 and (
        left_compact in right_compact or right_compact in left_compact
    ):
        return True
    return SequenceMatcher(None, left_compact, right_compact, autojunk=False).ratio() >= threshold


def _last_seen_timestamp(item: dict[str, Any]) -> float:
    value = item.get("lastSeenAt")
    if not isinstance(value, str):
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def deduplicate_similar_candidates(
    candidates: list[dict[str, Any]], threshold: float
) -> tuple[list[dict[str, Any]], int]:
    """Keep the first ranked representative and attach its close variants."""
    if not 0.5 <= threshold <= 1.0:
        raise ValueError("similarity threshold must be between 0.5 and 1.0")

    representatives: list[dict[str, Any]] = []
    family_texts: list[list[str]] = []
    merged = 0
    for candidate in candidates:
        normalized = str(candidate["normalizedText"])
        for index, representative in enumerate(representatives):
            if any(_near_duplicate(normalized, member, threshold) for member in family_texts[index]):
                variants = representative.setdefault("similarVariants", [])
                variants.append({
                    "text": candidate["text"],
                    "normalizedText": normalized,
                    "count": candidate["count"],
                    "uniqueUsers": candidate["uniqueUsers"],
                })
                representative["familyCount"] = int(
                    representative.get("familyCount", representative["count"])
                ) + int(candidate["count"])
                family_texts[index].append(normalized)
                merged += 1
                break
        else:
            representatives.append(dict(candidate))
            family_texts.append([normalized])
    representatives.sort(key=lambda item: (
        -int(item.get("familyCount", item["count"])),
        -int(item["count"]),
        -int(item["uniqueUsers"]),
        -_last_seen_timestamp(item),
        abs(len(str(item["normalizedText"])) - 12),
        str(item["normalizedText"]),
    ))
    return representatives, merged


def build_candidates(
    database: DanmakuDatabase,
    room_id: int,
    window_hours: int,
    min_count: int,
    max_candidates: int,
    existing_index_path: Path,
    similarity_threshold: float | None = DEFAULT_SIMILARITY_THRESHOLD,
    memes_path: Path | None = None,
    review_state_path: Path | None = None,
) -> dict[str, Any]:
    end = iso_now()
    start = end - timedelta(hours=window_hours)
    raw_count, rows = database.aggregate_since(room_id, start)
    session_rows = database.session_occurrences(room_id, start)
    occurrences_by_text: dict[str, list[dict[str, Any]]] = {}
    for row in session_rows:
        first_seen = str(row["first_seen_at"])
        occurrences_by_text.setdefault(str(row["normalized_content"]), []).append({
            "sessionId": str(row["session_id"]),
            "date": datetime.fromisoformat(first_seen).astimezone(SHANGHAI).date().isoformat(),
            "count": int(row["count"]),
            "firstSeenAt": first_seen,
            "lastSeenAt": str(row["last_seen_at"]),
        })
    index = read_json(existing_index_path, {"items": {}})
    existing = index.get("items", {})
    existing_keys = set(existing) if isinstance(existing, dict) else set()
    local_meme_keys = _local_meme_keys(memes_path)
    reviewed_keys = local_meme_keys | _rejected_keys(review_state_path)
    existing_buckets = _reference_buckets(existing_keys)
    reviewed_buckets = _reference_buckets(reviewed_keys)
    existing_filtered = 0
    existing_similar_filtered = 0
    local_meme_filtered = 0
    reviewed_similar_filtered = 0
    short_filtered = 0
    activity_filtered = 0
    meaningless_filtered = 0
    candidates: list[dict[str, Any]] = []

    for row in rows:
        normalized = str(row["normalized_content"])
        count = int(row["count"])
        if normalized in existing_keys:
            existing_filtered += 1
            continue
        if similarity_threshold is not None and _near_reference(
            normalized, existing_buckets, similarity_threshold
        ):
            existing_similar_filtered += 1
            continue
        if normalized in local_meme_keys:
            local_meme_filtered += 1
            continue
        if similarity_threshold is not None and _near_reference(
            normalized, reviewed_buckets, similarity_threshold
        ):
            reviewed_similar_filtered += 1
            continue
        if _is_activity_text(normalized):
            activity_filtered += 1
            continue
        if len(normalized) < MIN_CANDIDATE_LENGTH:
            short_filtered += 1
            continue
        if not has_meaningful_content(normalized) or len(_comparison_text(normalized)) < 2:
            meaningless_filtered += 1
            continue
        source: str | None = "high_frequency" if count >= min_count else None
        if source is None and count == 1 and len(normalized) >= 20:
            source = "long_text"
        if source is None:
            continue
        candidate = {
            "text": row["text"], "normalizedText": normalized, "count": count,
            "uniqueUsers": int(row["unique_users"]), "firstSeenAt": row["first_seen_at"],
            "lastSeenAt": row["last_seen_at"], "source": source,
        }
        if occurrences := occurrences_by_text.get(normalized):
            candidate["collectionOccurrences"] = occurrences
        candidates.append(candidate)

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
        "existingSimilarFilteredCount": existing_similar_filtered,
        "localMemeFilteredCount": local_meme_filtered,
        "reviewedSimilarFilteredCount": reviewed_similar_filtered,
        "shortFilteredCount": short_filtered, "activityFilteredCount": activity_filtered,
        "meaninglessFilteredCount": meaningless_filtered,
    }
    if similarity_threshold is not None:
        candidates, merged = deduplicate_similar_candidates(candidates, similarity_threshold)
        result["similarityDeduplication"] = {
            "threshold": similarity_threshold,
            "mergedCandidates": merged,
        }
    result["candidates"] = candidates[:max(0, max_candidates)]
    return result
