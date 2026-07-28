import asyncio
import json
import threading
import time
from pathlib import Path

import pytest

from danmaku_meme_finder import admin
from danmaku_meme_finder.admin import (
    AdminService,
    AdminSettings,
    CollectionStart,
    DocumentUpdate,
    ReviewAction,
)
from danmaku_meme_finder.exporter import write_json_atomic


def make_service(root: Path) -> AdminService:
    data = root / "data"
    write_json_atomic(
        data / "candidates.json",
        {
            "generatedAt": "2026-07-26T10:00:00+08:00",
            "candidates": [
                {
                    "text": "新的直播间梗",
                    "normalizedText": "新的直播间梗",
                    "count": 8,
                    "uniqueUsers": 5,
                    "source": "high_frequency",
                }
            ],
        },
    )
    write_json_atomic(data / "memes.json", {"updatedAt": None, "roomId": 6657, "memes": []})
    write_json_atomic(data / "catalog" / "active.json", {"items": []})
    write_json_atomic(data / "catalog" / "manifest.json", {"total": 0, "archives": []})
    write_json_atomic(data / "existing_index.json", {"total": 0, "items": {}})
    write_json_atomic(data / "events.json", {"schemaVersion": 1, "events": []})
    write_json_atomic(data / "sessions.json", {"schemaVersion": 1, "sessions": []})
    write_json_atomic(data / "tags.json", {"schemaVersion": 1, "tags": {"06": {"label": "群魔乱舞"}}})
    write_json_atomic(data / "monthly-reports" / "index.json", {"schemaVersion": 1, "reports": []})
    return AdminService(AdminSettings(root))


def test_admin_approves_candidate_without_rebuilding_catalog(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    result = service.review(
        ReviewAction(key="新的直播间梗", decision="approve", tags=["06"])
    )

    assert result["created"] is True
    assert result["catalogId"] == "00001"
    assert result["state"]["counts"]["pending"] == 0
    memes = json.loads((tmp_path / "data" / "memes.json").read_text(encoding="utf-8"))
    assert memes["memes"][0]["tags"] == ["06"]
    catalog = json.loads((tmp_path / "data" / "catalog" / "active.json").read_text(encoding="utf-8"))
    assert catalog == {"items": []}


def test_admin_rejection_stays_local(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    result = service.review(ReviewAction(key="新的直播间梗", decision="reject"))

    assert result["state"]["counts"]["pending"] == 0
    state = json.loads((tmp_path / "data" / "review_state.json").read_text(encoding="utf-8"))
    assert "新的直播间梗" in state["rejected"]
    assert json.loads((tmp_path / "data" / "memes.json").read_text(encoding="utf-8"))["memes"] == []


def test_admin_report_save_updates_index(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    report = {
        "schemaVersion": 1,
        "id": "monthly-2026-08",
        "month": "2026-08",
        "title": "2026年8月总结",
        "publishedAt": "2026-08-31",
        "coverUrl": "/covers/reports/2026-08.png",
        "summary": "测试月报",
        "sections": [],
    }

    result = service.save_document(DocumentUpdate(key="report:2026-08", payload=report))

    assert result["saved"] == "report:2026-08"
    index = json.loads((tmp_path / "data" / "monthly-reports" / "index.json").read_text(encoding="utf-8"))
    assert index["reports"][0]["file"] == "monthly-reports/2026-08.json"


def test_admin_rejects_report_with_mismatched_month(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    with pytest.raises(ValueError, match="month"):
        service.save_document(
            DocumentUpdate(
                key="report:2026-08",
                payload={
                    "id": "monthly-2026-07",
                    "month": "2026-07",
                    "title": "wrong",
                    "publishedAt": "2026-07-31",
                    "summary": "",
                    "sections": [],
                },
            )
        )


def test_admin_validates_new_events_and_sessions(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.save_document(DocumentUpdate(key="events", payload={
        "schemaVersion": 1,
        "events": [{
            "id": "event-2026", "title": "Event", "startDate": "2026-08-01", "endDate": "2026-08-03"
        }],
    }))
    service.save_document(DocumentUpdate(key="sessions", payload={
        "schemaVersion": 1,
        "sessions": [{"id": "session-a", "date": "2026-08-01", "title": "Live"}],
    }))

    with pytest.raises(ValueError, match="duplicate events id"):
        service.save_document(DocumentUpdate(key="events", payload={
            "events": [
                {"id": "same", "title": "A", "startDate": "2026-08-01", "endDate": "2026-08-02"},
                {"id": "same", "title": "B", "startDate": "2026-08-03", "endDate": "2026-08-04"},
            ]
        }))


def test_admin_publish_rebuilds_catalog_and_uses_explicit_files(monkeypatch, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    service.review(ReviewAction(key="新的直播间梗", decision="approve", tags=["06"]))
    published: dict[str, object] = {}

    def fake_publish(root: Path, files: list[Path], message: str) -> str:
        published.update(root=root, files=files, message=message)
        return message

    monkeypatch.setattr(admin, "publish_files", fake_publish)

    result = service.publish()

    assert result["published"] is True
    assert result["catalogItems"] == 1
    assert published["root"] == tmp_path
    assert tmp_path / "data" / "catalog" in published["files"]
    assert tmp_path / "data" / "trends" / "daily.json" in published["files"]
    assert published["message"] == "Update managed site content"


def test_admin_ui_exposes_event_and_session_creation() -> None:
    static = Path(__file__).parents[1] / "src" / "danmaku_meme_finder" / "admin_static"
    html = (static / "index.html").read_text(encoding="utf-8")
    script = (static / "app.js").read_text(encoding="utf-8")

    assert 'id="new-event-button"' in html
    assert 'id="new-session-button"' in html
    assert "async function createEvent()" in script
    assert "async function createSession()" in script


def test_admin_collection_start_conflict_and_graceful_stop(monkeypatch, tmp_path: Path) -> None:
    service = make_service(tmp_path)
    started = threading.Event()
    finalized = threading.Event()

    async def fake_collection(settings, salt, root):  # type: ignore[no-untyped-def]
        assert settings.duration_seconds == 180
        assert root == tmp_path
        started.set()
        try:
            await asyncio.Future()
        finally:
            finalized.set()

    monkeypatch.setattr(admin, "run_collection", fake_collection)

    result = service.start_collection(CollectionStart(durationSeconds=180))
    assert result["collection"]["active"] is True
    assert started.wait(timeout=2)
    with pytest.raises(ValueError, match="已经在运行"):
        service.start_collection(CollectionStart(durationSeconds=60))

    stopping = service.stop_collection()["collection"]
    assert stopping["phase"] == "stopping"
    assert finalized.wait(timeout=2)
    deadline = time.monotonic() + 2
    while service.collection.status()["active"] and time.monotonic() < deadline:
        time.sleep(0.01)
    status = service.collection.status()
    assert status["phase"] == "stopped"
    assert status["active"] is False
    assert status["candidateCount"] == 1
    service.collection.close()


def test_admin_collection_requires_existing_index(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    (tmp_path / "data" / "existing_index.json").unlink()

    with pytest.raises(ValueError, match="sync-existing"):
        service.start_collection(CollectionStart(durationSeconds=60))


def test_admin_ui_exposes_collection_controls() -> None:
    static = Path(__file__).parents[1] / "src" / "danmaku_meme_finder" / "admin_static"
    html = (static / "index.html").read_text(encoding="utf-8")
    script = (static / "app.js").read_text(encoding="utf-8")

    assert 'data-view="collection"' in html
    assert 'id="start-collection-button"' in html
    assert 'id="stop-collection-button"' in html
    assert 'request("/api/collection/start"' in script
    assert 'request("/api/collection/stop"' in script
