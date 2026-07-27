"""Pydantic data shapes shared by the package."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IncomingDanmaku(BaseModel):
    room_id: int
    content: str
    user_id: str | None = None
    session_id: str | None = None
    sent_at: datetime


class StoredDanmaku(BaseModel):
    room_id: int
    content: str
    normalized_content: str
    user_key: str | None = None
    session_id: str | None = None
    sent_at: datetime
    collected_at: datetime


class ExistingMeme(BaseModel):
    id: int
    barrage: str
    cnt: int = 0
    tags: list[str] = Field(default_factory=list)
    submit_time: str | None = None


class CollectionOccurrence(BaseModel):
    sessionId: str
    date: str
    count: int
    firstSeenAt: str
    lastSeenAt: str


class Candidate(BaseModel):
    text: str
    normalizedText: str
    count: int
    uniqueUsers: int
    firstSeenAt: str
    lastSeenAt: str
    source: str
    collectionOccurrences: list[CollectionOccurrence] = Field(default_factory=list)
