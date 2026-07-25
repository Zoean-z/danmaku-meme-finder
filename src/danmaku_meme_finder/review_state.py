"""Local-only decisions that keep reviewed candidates out of the next queue."""

from __future__ import annotations

from typing import Any

from .database import iso_now
from .normalize import normalize_text


def candidate_key(candidate: dict[str, Any]) -> str:
    normalized = candidate.get("normalizedText")
    if isinstance(normalized, str) and normalized:
        return normalized
    text = candidate.get("text")
    return normalize_text(text) if isinstance(text, str) else ""


def confirmed_keys(memes: dict[str, Any]) -> set[str]:
    records = memes.get("memes", [])
    if not isinstance(records, list):
        return set()
    return {
        normalize_text(record["text"])
        for record in records
        if isinstance(record, dict) and isinstance(record.get("text"), str) and normalize_text(record["text"])
    }


def rejected_keys(state: dict[str, Any]) -> set[str]:
    rejected = state.get("rejected", {})
    return set(rejected) if isinstance(rejected, dict) else set()


def review_queue(
    candidates: list[dict[str, Any]], memes: dict[str, Any], state: dict[str, Any]
) -> list[dict[str, Any]]:
    excluded = confirmed_keys(memes) | rejected_keys(state)
    return [candidate for candidate in candidates if candidate_key(candidate) not in excluded]


def reject_candidate(state: dict[str, Any], candidate: dict[str, Any]) -> None:
    key = candidate_key(candidate)
    if not key:
        raise ValueError("candidate has no normalized text")
    rejected = state.setdefault("rejected", {})
    if not isinstance(rejected, dict):
        raise ValueError("rejected review state must be an object")
    rejected[key] = {
        "text": candidate.get("text"),
        "rejectedAt": iso_now().isoformat(),
    }
    state["schemaVersion"] = 1
    state["updatedAt"] = iso_now().isoformat()
