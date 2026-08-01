"""Small localhost-only browser workspace for reviewing and publishing data."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import webbrowser
from dataclasses import dataclass
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .catalog import (
    build_catalog,
    format_catalog_id,
    load_distributed_catalog,
    next_catalog_number,
    write_distributed_catalog,
)
from .curation import add_confirmed_meme, resolve_tags, tag_labels
from .collection_runner import CollectionSettings, run_collection
from .cleanup import cleanup_reviewed_sessions, reviewed_session_ids
from .config import user_hash_salt
from .database import DanmakuDatabase
from .exporter import read_json, write_json_atomic
from .publication import publish_files
from .review_state import candidate_key, reject_candidate, review_queue
from .sessions import refresh_session_provenance

LOGGER = logging.getLogger(__name__)
DATE_VALUE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_REQUEST_BYTES = 8 * 1024 * 1024


class ReviewAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    decision: Literal["approve", "reject", "reject_similar"]
    tags: list[str] = Field(default_factory=list)


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    payload: dict[str, Any]


class CollectionStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    durationSeconds: int | None = Field(default=1800, ge=1, le=12 * 60 * 60)


@dataclass(frozen=True)
class AdminSettings:
    root: Path
    room_id: int = 6657

    def data(self, name: str) -> Path:
        return self.root / "data" / name


class CollectionController:
    """Run at most one existing collection workflow behind the local admin."""

    def __init__(self, settings: AdminSettings) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[dict[str, Any]] | None = None
        self._stop_requested = False
        self._state: dict[str, Any] = {
            "phase": "idle",
            "active": False,
            "startedAt": None,
            "finishedAt": None,
            "durationSeconds": None,
            "sessionId": None,
            "importedMessages": 0,
            "candidateCount": None,
            "error": None,
        }

    def start(self, request: CollectionStart) -> dict[str, Any]:
        with self._lock:
            if self._state["active"]:
                raise ValueError("弹幕采集已经在运行")
            if not self.settings.data("existing_index.json").is_file():
                raise ValueError("缺少 data/existing_index.json，请先运行 sync-existing")
            self._stop_requested = False
            self._state = {
                "phase": "running",
                "active": True,
                "startedAt": datetime.now().astimezone().isoformat(),
                "finishedAt": None,
                "durationSeconds": request.durationSeconds,
                "sessionId": None,
                "importedMessages": 0,
                "candidateCount": None,
                "error": None,
            }
            self._thread = threading.Thread(
                target=self._thread_main,
                args=(request.durationSeconds,),
                name="danmaku-admin-collector",
                daemon=True,
            )
            self._thread.start()
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if not self._state["active"]:
                raise ValueError("当前没有正在运行的弹幕采集")
            self._state["phase"] = "stopping"
            self._stop_requested = True
            if self._loop is not None and self._task is not None:
                self._loop.call_soon_threadsafe(self._task.cancel)
            return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_metrics_locked()
            return dict(self._state)

    def close(self) -> None:
        with self._lock:
            active = bool(self._state["active"])
        if active:
            self.stop()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=10)

    def _thread_main(self, duration_seconds: int | None) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        settings = CollectionSettings(
            room_id=self.settings.room_id,
            database_path=self.settings.data("danmaku.db"),
            input_path=self.settings.data("live.jsonl"),
            checkpoint_path=self.settings.data("live.import.checkpoint.json"),
            existing_index_path=self.settings.data("existing_index.json"),
            memes_path=self.settings.data("memes.json"),
            output_path=self.settings.data("candidates.json"),
            sessions_path=self.settings.data("sessions.json"),
            review_state_path=self.settings.data("review_state.json"),
            duration_seconds=duration_seconds,
        )
        task = loop.create_task(run_collection(settings, user_hash_salt(), self.settings.root))
        with self._lock:
            self._loop = loop
            self._task = task
            if self._stop_requested:
                task.cancel()
        try:
            result = loop.run_until_complete(task)
            with self._lock:
                self._state["phase"] = "completed"
                self._state["sessionId"] = result["session"].get("id")
                self._state["importedMessages"] = result["import"].get("imported", 0)
                self._state["candidateCount"] = len(result["candidates"].get("candidates", []))
        except asyncio.CancelledError:
            with self._lock:
                self._state["phase"] = "stopped"
        except Exception as exc:  # pragma: no cover - boundary is exercised through state
            LOGGER.exception("Admin collection failed")
            with self._lock:
                self._state["phase"] = "failed"
                self._state["error"] = str(exc)
        finally:
            with self._lock:
                self._state["active"] = False
                self._state["finishedAt"] = datetime.now().astimezone().isoformat()
                self._refresh_metrics_locked()
                self._task = None
                self._loop = None
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    def _refresh_metrics_locked(self) -> None:
        session_id = self._state.get("sessionId")
        sessions = read_json(self.settings.data("sessions.json"), {"sessions": []}).get("sessions", [])
        started_at = str(self._state.get("startedAt") or "")
        if started_at and not session_id and isinstance(sessions, list):
            matching = [
                item for item in sessions
                if isinstance(item, dict) and str(item.get("observedStartedAt") or "") >= started_at
            ]
            if matching:
                session_id = str(matching[-1].get("id") or "") or None
                self._state["sessionId"] = session_id
        database_path = self.settings.data("danmaku.db")
        if session_id and database_path.is_file():
            try:
                with DanmakuDatabase(database_path) as database:
                    self._state["importedMessages"] = database.session_message_count(session_id)
            except OSError:
                LOGGER.warning("Could not read collection progress from SQLite", exc_info=True)
        if started_at and not self._state["active"] and self._state.get("candidateCount") is None:
            candidates = read_json(self.settings.data("candidates.json"), {"candidates": []}).get("candidates", [])
            if isinstance(candidates, list):
                self._state["candidateCount"] = len(candidates)


class AdminService:
    """Own file mutations so HTTP and tests share the same safety rules."""

    def __init__(self, settings: AdminSettings) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self.collection = CollectionController(settings)

    def state(self) -> dict[str, Any]:
        with self._lock:
            candidate_payload = read_json(self.settings.data("candidates.json"), {"candidates": []})
            raw_candidates = candidate_payload.get("candidates", [])
            candidates = [item for item in raw_candidates if isinstance(item, dict)] if isinstance(raw_candidates, list) else []
            memes = read_json(self.settings.data("memes.json"), {"roomId": self.settings.room_id, "memes": []})
            review_state = read_json(
                self.settings.data("review_state.json"), {"schemaVersion": 1, "rejected": {}}
            )
            queue = review_queue(candidates, memes, review_state)
            documents = self._documents()
            return {
                "roomId": self.settings.room_id,
                "generatedAt": candidate_payload.get("generatedAt"),
                "queue": queue,
                "counts": {
                    "candidates": len(candidates),
                    "pending": len(queue),
                    "approved": self._collection_size(memes, "memes"),
                    "rejected": self._collection_size(review_state, "rejected"),
                    "events": self._collection_size(documents["events"], "events"),
                    "sessions": self._collection_size(documents["sessions"], "sessions"),
                },
                "tags": tag_labels(documents["tags"]),
                "documents": [
                    {"key": key, "label": self._document_label(key), "payload": payload}
                    for key, payload in documents.items()
                ],
                "collection": self.collection.status(),
            }

    def start_collection(self, request: CollectionStart) -> dict[str, Any]:
        return {"collection": self.collection.start(request)}

    def stop_collection(self) -> dict[str, Any]:
        return {"collection": self.collection.stop()}

    def review(self, action: ReviewAction) -> dict[str, Any]:
        with self._lock:
            candidate_payload = read_json(self.settings.data("candidates.json"), {"candidates": []})
            raw_candidates = candidate_payload.get("candidates", [])
            candidates = [item for item in raw_candidates if isinstance(item, dict)] if isinstance(raw_candidates, list) else []
            candidate = next((item for item in candidates if candidate_key(item) == action.key), None)
            if candidate is None:
                raise ValueError("candidate is no longer in the current snapshot")

            memes_path = self.settings.data("memes.json")
            memes = read_json(memes_path, {"roomId": self.settings.room_id, "memes": []})
            review_state_path = self.settings.data("review_state.json")
            review_state = read_json(review_state_path, {"schemaVersion": 1, "rejected": {}})
            if candidate not in review_queue([candidate], memes, review_state):
                raise ValueError("candidate was already reviewed")

            if action.decision in {"reject", "reject_similar"}:
                reject_candidate(
                    review_state,
                    candidate,
                    exclude_similar=action.decision == "reject_similar",
                )
                write_json_atomic(review_state_path, review_state)
                return {"decision": action.decision, "created": False, "state": self.state()}

            labels = tag_labels(read_json(self.settings.data("tags.json"), {"tags": {}}))
            resolved = resolve_tags(",".join(action.tags), labels)
            if not resolved:
                raise ValueError("select at least one tag before approving")
            existing = read_json(self.settings.data("existing_index.json"), {"items": {}})
            catalog = load_distributed_catalog(self.settings.data("catalog"))
            catalog_id = format_catalog_id(next_catalog_number(catalog, existing, memes))
            memes.setdefault("roomId", self.settings.room_id)
            memes, created = add_confirmed_meme(memes, candidate, resolved, catalog_id)
            write_json_atomic(memes_path, memes)
            return {
                "decision": "approve",
                "created": created,
                "catalogId": catalog_id,
                "state": self.state(),
            }

    def save_document(self, update: DocumentUpdate) -> dict[str, Any]:
        with self._lock:
            path = self._document_path(update.key)
            self._validate_document(update.key, update.payload)
            write_json_atomic(path, update.payload)
            return {"saved": update.key, "state": self.state()}

    def publish(self) -> dict[str, Any]:
        with self._lock:
            collection_state = self.collection.status()
            if collection_state["active"]:
                raise ValueError("采集仍在运行，停止并完成落库后才能发布")
            existing_path = self.settings.data("existing_index.json")
            if not existing_path.is_file():
                raise ValueError("缺少 data/existing_index.json，请先运行 sync-existing 再发布")
            memes_path = self.settings.data("memes.json")
            sessions_path = self.settings.data("sessions.json")
            catalog_path = self.settings.data("catalog")
            legacy_catalog_path = self.settings.data("catalog.json")
            trends_path = self.settings.data("trends/daily.json")
            existing = read_json(existing_path, {"items": {}, "total": 0})
            memes = read_json(memes_path, {"roomId": self.settings.room_id, "memes": []})
            candidate_payload = read_json(self.settings.data("candidates.json"), {"candidates": []})
            raw_candidates = candidate_payload.get("candidates", [])
            candidates = [item for item in raw_candidates if isinstance(item, dict)] if isinstance(raw_candidates, list) else []
            review_state = read_json(
                self.settings.data("review_state.json"), {"schemaVersion": 1, "rejected": {}}
            )
            pending = review_queue(candidates, memes, review_state)
            if pending:
                raise ValueError(f"还有 {len(pending)} 条候选未审核，全部处理后才能发布和清理原始弹幕")
            cleanup_sessions = reviewed_session_ids(candidate_payload)
            sessions = read_json(sessions_path, {"schemaVersion": 1, "sessions": []})
            database_path = self.settings.data("danmaku.db")
            if database_path.is_file():
                with DanmakuDatabase(database_path) as database:
                    refresh_session_provenance(sessions, memes, database, self.settings.room_id)
            else:
                refresh_session_provenance(sessions, memes, None, self.settings.room_id)
            write_json_atomic(memes_path, memes)
            write_json_atomic(sessions_path, sessions)
            previous = load_distributed_catalog(catalog_path)
            catalog = build_catalog(existing, memes, self.settings.room_id, previous)
            manifest = write_distributed_catalog(catalog, catalog_path, trends_path, sessions)
            if legacy_catalog_path.is_file():
                legacy_catalog_path.unlink()

            public_files = [
                memes_path,
                catalog_path,
                trends_path,
                self.settings.data("events.json"),
                sessions_path,
                self.settings.data("tags.json"),
            ]
            message = publish_files(self.settings.root, public_files, "Update managed site content")
            cleanup = cleanup_reviewed_sessions(
                database_path,
                self.settings.data("live.jsonl"),
                self.settings.data("live.import.checkpoint.json"),
                cleanup_sessions,
            )
            return {
                "published": message is not None,
                "message": message or "没有需要发布的公开数据变更",
                "catalogItems": manifest["total"],
                "cleanup": cleanup,
                "state": self.state(),
            }

    def _documents(self) -> dict[str, dict[str, Any]]:
        documents = {
            "events": read_json(self.settings.data("events.json"), {"schemaVersion": 1, "events": []}),
            "sessions": read_json(self.settings.data("sessions.json"), {"schemaVersion": 1, "sessions": []}),
            "tags": read_json(self.settings.data("tags.json"), {"schemaVersion": 1, "tags": {}}),
            "memes": read_json(
                self.settings.data("memes.json"), {"updatedAt": None, "roomId": self.settings.room_id, "memes": []}
            ),
        }
        return documents

    def _document_path(self, key: str) -> Path:
        fixed = {
            "events": self.settings.data("events.json"),
            "sessions": self.settings.data("sessions.json"),
            "tags": self.settings.data("tags.json"),
            "memes": self.settings.data("memes.json"),
        }
        if key in fixed:
            return fixed[key]
        raise ValueError(f"unknown managed document: {key}")

    @staticmethod
    def _validate_document(key: str, payload: dict[str, Any]) -> None:
        expected: dict[str, tuple[str, type]] = {
            "events": ("events", list),
            "sessions": ("sessions", list),
            "tags": ("tags", dict),
            "memes": ("memes", list),
        }
        if key in expected:
            field, kind = expected[key]
            if not isinstance(payload.get(field), kind):
                raise ValueError(f"{key} must contain {field} as {kind.__name__}")
            if key == "events":
                AdminService._validate_records(payload[field], key, ("id", "title", "startDate", "endDate"))
                for record in payload[field]:
                    if not DATE_VALUE.fullmatch(record["startDate"]) or not DATE_VALUE.fullmatch(record["endDate"]):
                        raise ValueError("event dates must use YYYY-MM-DD")
                    try:
                        date.fromisoformat(record["startDate"])
                        date.fromisoformat(record["endDate"])
                    except ValueError as exc:
                        raise ValueError("event dates must be valid calendar dates") from exc
                    if record["startDate"] > record["endDate"]:
                        raise ValueError("event startDate must not be after endDate")
            elif key == "sessions":
                AdminService._validate_records(payload[field], key, ("id", "date", "title"))
                for record in payload[field]:
                    if not DATE_VALUE.fullmatch(record["date"]):
                        raise ValueError("session date must use YYYY-MM-DD")
                    try:
                        date.fromisoformat(record["date"])
                    except ValueError as exc:
                        raise ValueError("session date must be a valid calendar date") from exc
            return
        raise ValueError(f"unknown managed document: {key}")

    @staticmethod
    def _validate_records(records: list[Any], label: str, required: tuple[str, ...]) -> None:
        identifiers: set[str] = set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f"{label} entries must be objects")
            for field in required:
                if not isinstance(record.get(field), str) or not record[field].strip():
                    raise ValueError(f"{label} field must be a non-empty string: {field}")
            identifier = record["id"]
            if identifier in identifiers:
                raise ValueError(f"duplicate {label} id: {identifier}")
            identifiers.add(identifier)

    @staticmethod
    def _collection_size(payload: dict[str, Any], field: str) -> int:
        value = payload.get(field)
        return len(value) if isinstance(value, (list, dict)) else 0

    @staticmethod
    def _document_label(key: str) -> str:
        labels = {
            "events": "赛事",
            "sessions": "直播场次",
            "tags": "标签",
            "memes": "正式梗库",
        }
        return labels.get(key, key)


class AdminRequestHandler(BaseHTTPRequestHandler):
    server: "AdminHttpServer"

    def do_GET(self) -> None:  # noqa: N802
        if not self._is_local_request():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        path = urlparse(self.path).path
        if path == "/api/state":
            self._send_json(HTTPStatus.OK, self.server.service.state())
            return
        if path == "/api/collection":
            self._send_json(HTTPStatus.OK, {"collection": self.server.service.collection.status()})
            return
        assets = {"/": "index.html", "/app.css": "app.css", "/app.js": "app.js"}
        name = assets.get(path)
        if name is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = "text/html; charset=utf-8" if name.endswith(".html") else (
            "text/css; charset=utf-8" if name.endswith(".css") else "text/javascript; charset=utf-8"
        )
        body = (Path(__file__).with_name("admin_static") / name).read_bytes()
        self._send(HTTPStatus.OK, content_type, body)

    def do_POST(self) -> None:  # noqa: N802
        if not self._is_local_request():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        origin = self.headers.get("Origin")
        if origin and origin not in {
            f"http://127.0.0.1:{self.server.server_port}",
            f"http://localhost:{self.server.server_port}",
        }:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/review":
                result = self.server.service.review(ReviewAction.model_validate(payload))
            elif path == "/api/documents":
                result = self.server.service.save_document(DocumentUpdate.model_validate(payload))
            elif path == "/api/publish":
                result = self.server.service.publish()
            elif path == "/api/collection/start":
                result = self.server.service.start_collection(CollectionStart.model_validate(payload))
            elif path == "/api/collection/stop":
                result = self.server.service.stop_collection()
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._send_json(HTTPStatus.OK, result)
        except (json.JSONDecodeError, ValidationError, ValueError, OSError, RuntimeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover - last-resort request boundary
            LOGGER.exception("Admin request failed")
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request body is empty or too large")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request JSON must be an object")
        return payload

    def _is_local_request(self) -> bool:
        host = self.headers.get("Host", "").partition(":")[0].lower()
        return host in {"127.0.0.1", "localhost"}

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self._send(status, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.info("admin %s", format % args)


class AdminHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], service: AdminService) -> None:
        self.service = service
        super().__init__(address, AdminRequestHandler)


def run_admin(root: Path, port: int, open_browser: bool = True) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("--port must be between 1 and 65535")
    service = AdminService(AdminSettings(root.resolve()))
    server = AdminHttpServer(("127.0.0.1", port), service)
    url = f"http://127.0.0.1:{port}"
    print(f"Local admin: {url}")
    print("Press Ctrl+C to stop. GitHub is only updated after clicking Publish.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        service.collection.close()
        server.server_close()
