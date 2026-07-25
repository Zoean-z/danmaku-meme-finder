"""Synchronize the public existing-meme index with bounded retries."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, Field, ValidationError

from .models import ExistingMeme
from .normalize import normalize_text

SHANGHAI = ZoneInfo("Asia/Shanghai")


class ApiMeme(BaseModel):
    id: int
    barrage: str
    cnt: int | str = 0
    tags: str | None = ""
    submitTime: str | None = None


class ApiData(BaseModel):
    records: list[Any] = Field(default_factory=list, validation_alias="list")


class ApiEnvelope(BaseModel):
    code: int
    data: ApiData


def _to_existing(item: ApiMeme) -> ExistingMeme:
    tags = [tag.strip() for tag in (item.tags or "").split(",") if tag.strip()]
    try:
        count = int(item.cnt)
    except (TypeError, ValueError):
        count = 0
    return ExistingMeme(id=item.id, barrage=item.barrage, cnt=count, tags=tags, submit_time=item.submitTime)


async def _get_page(
    client: httpx.AsyncClient, url: str, page_num: int, page_size: int, retries: int
) -> list[dict[str, Any]]:
    error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = await client.get(url, params={"pageNum": page_num, "pageSize": page_size})
            response.raise_for_status()
            payload = ApiEnvelope.model_validate(response.json())
            if payload.code != 200:
                raise RuntimeError(f"Existing API returned code {payload.code}")
            return payload.data.records
        except (httpx.HTTPError, ValidationError, ValueError, RuntimeError) as exc:
            error = exc
            if attempt == retries:
                break
            await asyncio.sleep(0.4 * (2**attempt))
    raise RuntimeError(f"Failed to fetch existing meme page {page_num}: {error}") from error


async def fetch_existing_index(
    url: str, page_size: int = 50, retries: int = 2, client: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Fetch every non-empty page and return the file-ready normalized index."""
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=httpx.Timeout(15.0), follow_redirects=True)
    assert client is not None
    items: dict[str, dict[str, object]] = {}
    total = 0
    try:
        page_num = 1
        while True:
            page = await _get_page(client, url, page_num, page_size, retries)
            for raw_item in page:
                try:
                    api_item = ApiMeme.model_validate(raw_item)
                    item = _to_existing(api_item)
                    normalized = normalize_text(item.barrage)
                    if normalized:
                        # A normalized form is only needed for membership; choosing the lowest ID is stable.
                        candidate = {
                            "id": item.id, "barrage": item.barrage, "cnt": item.cnt,
                            "tags": item.tags, "submitTime": item.submit_time,
                        }
                        current = items.get(normalized)
                        if current is None or item.id < int(current["id"]):
                            items[normalized] = candidate
                    total += 1
                except (ValidationError, TypeError, ValueError):
                    # A malformed item should not lose the rest of a page.
                    continue
            if not page or len(page) < page_size:
                break
            page_num += 1
    finally:
        if own_client:
            await client.aclose()
    return {
        "updatedAt": datetime.now(SHANGHAI).isoformat(),
        "total": total,
        "items": dict(sorted(items.items())),
    }
