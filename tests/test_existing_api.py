import httpx
import asyncio

from danmaku_meme_finder.existing_api import fetch_existing_index


def response(records: list[dict[str, object]]) -> httpx.Response:
    return httpx.Response(200, json={"code": 200, "data": {"list": records}})


def test_fetch_existing_index_paginates_and_normalizes() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["pageNum"])
        calls.append(page)
        if page == 1:
            return response([
                {"id": 2, "barrage": "新 梗！！", "cnt": "3", "tags": "06, 24", "submitTime": "now"},
                {"id": 1, "barrage": "旧梗", "cnt": "7", "tags": "", "submitTime": None},
            ])
        return response([{"id": 3, "barrage": "最后一条", "cnt": "1", "tags": "x"}])

    async def run() -> dict[str, object]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_existing_index("https://example.test/page", page_size=2, client=client)

    index = asyncio.run(run())

    assert calls == [1, 2]
    assert index["total"] == 3
    assert index["items"]["新 梗!!"]["tags"] == ["06", "24"]


def test_empty_page_ends_pagination() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response([])

    async def run() -> dict[str, object]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_existing_index("https://example.test/page", client=client)

    index = asyncio.run(run())

    assert calls == 1
    assert index["total"] == 0


def test_request_error_is_retried() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return response([])

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await fetch_existing_index("https://example.test/page", retries=1, client=client)

    asyncio.run(run())

    assert calls == 2


def test_malformed_item_does_not_discard_the_page() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return response([
            {"id": "not-an-int", "barrage": "bad"},
            {"id": 4, "barrage": "usable", "cnt": "2", "tags": "a"},
        ])

    async def run() -> dict[str, object]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_existing_index("https://example.test/page", page_size=50, client=client)

    index = asyncio.run(run())
    assert index["total"] == 1
    assert set(index["items"]) == {"usable"}
