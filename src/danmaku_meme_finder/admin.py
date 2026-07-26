"""Small localhost-only browser workspace for reviewing and publishing data."""

from __future__ import annotations

import json
import logging
import re
import threading
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .catalog import build_catalog, format_catalog_id, next_catalog_number
from .curation import add_confirmed_meme, resolve_tags, tag_labels
from .exporter import read_json, write_json_atomic
from .publication import publish_files
from .review_state import candidate_key, reject_candidate, review_queue

LOGGER = logging.getLogger(__name__)
REPORT_KEY = re.compile(r"^report:(\d{4}-\d{2})$")
MAX_REQUEST_BYTES = 8 * 1024 * 1024


class ReviewAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    decision: Literal["approve", "reject"]
    tags: list[str] = Field(default_factory=list)


class DocumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    payload: dict[str, Any]


@dataclass(frozen=True)
class AdminSettings:
    root: Path
    room_id: int = 6657

    def data(self, name: str) -> Path:
        return self.root / "data" / name


class AdminService:
    """Own file mutations so HTTP and tests share the same safety rules."""

    def __init__(self, settings: AdminSettings) -> None:
        self.settings = settings
        self._lock = threading.RLock()

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
                    "reports": len([key for key in documents if key.startswith("report:")]),
                },
                "tags": tag_labels(documents["tags"]),
                "documents": [
                    {"key": key, "label": self._document_label(key), "payload": payload}
                    for key, payload in documents.items()
                ],
            }

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

            if action.decision == "reject":
                reject_candidate(review_state, candidate)
                write_json_atomic(review_state_path, review_state)
                return {"decision": "reject", "created": False, "state": self.state()}

            labels = tag_labels(read_json(self.settings.data("tags.json"), {"tags": {}}))
            resolved = resolve_tags(",".join(action.tags), labels)
            if not resolved:
                raise ValueError("select at least one tag before approving")
            existing = read_json(self.settings.data("existing_index.json"), {"items": {}})
            catalog = read_json(self.settings.data("catalog.json"), {"items": []})
            catalog_id = format_catalog_id(next_catalog_number(catalog, existing))
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
            if update.key.startswith("report:"):
                self._upsert_report_index(update.payload)
            return {"saved": update.key, "state": self.state()}

    def publish(self) -> dict[str, Any]:
        with self._lock:
            existing_path = self.settings.data("existing_index.json")
            if not existing_path.is_file():
                raise ValueError("缺少 data/existing_index.json，请先运行 sync-existing 再发布")
            memes_path = self.settings.data("memes.json")
            catalog_path = self.settings.data("catalog.json")
            existing = read_json(existing_path, {"items": {}, "total": 0})
            memes = read_json(memes_path, {"roomId": self.settings.room_id, "memes": []})
            previous = read_json(catalog_path, {"items": []})
            catalog = build_catalog(existing, memes, self.settings.room_id, previous)
            write_json_atomic(catalog_path, catalog)

            public_files = [
                memes_path,
                catalog_path,
                self.settings.data("events.json"),
                self.settings.data("sessions.json"),
                self.settings.data("tags.json"),
                self.settings.data("monthly-reports/index.json"),
                *sorted((self.settings.data("monthly-reports")).glob("????-??.json")),
            ]
            message = publish_files(self.settings.root, public_files, "Update managed site content")
            return {
                "published": message is not None,
                "message": message or "没有需要发布的公开数据变更",
                "catalogItems": catalog["summary"]["mergedItems"],
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
            "report-index": read_json(
                self.settings.data("monthly-reports/index.json"), {"schemaVersion": 1, "reports": []}
            ),
        }
        report_dir = self.settings.data("monthly-reports")
        if report_dir.is_dir():
            for path in sorted(report_dir.glob("????-??.json"), reverse=True):
                documents[f"report:{path.stem}"] = read_json(path, {})
        return documents

    def _document_path(self, key: str) -> Path:
        fixed = {
            "events": self.settings.data("events.json"),
            "sessions": self.settings.data("sessions.json"),
            "tags": self.settings.data("tags.json"),
            "memes": self.settings.data("memes.json"),
            "report-index": self.settings.data("monthly-reports/index.json"),
        }
        if key in fixed:
            return fixed[key]
        match = REPORT_KEY.fullmatch(key)
        if match:
            return self.settings.data(f"monthly-reports/{match.group(1)}.json")
        raise ValueError(f"unknown managed document: {key}")

    @staticmethod
    def _validate_document(key: str, payload: dict[str, Any]) -> None:
        expected: dict[str, tuple[str, type]] = {
            "events": ("events", list),
            "sessions": ("sessions", list),
            "tags": ("tags", dict),
            "memes": ("memes", list),
            "report-index": ("reports", list),
        }
        if key in expected:
            field, kind = expected[key]
            if not isinstance(payload.get(field), kind):
                raise ValueError(f"{key} must contain {field} as {kind.__name__}")
            return
        match = REPORT_KEY.fullmatch(key)
        if not match:
            raise ValueError(f"unknown managed document: {key}")
        if payload.get("month") != match.group(1):
            raise ValueError("report month must match its document key")
        for field in ("id", "title", "publishedAt", "summary"):
            if not isinstance(payload.get(field), str):
                raise ValueError(f"report field must be a string: {field}")
        if not isinstance(payload.get("sections"), list):
            raise ValueError("report sections must be a list")

    def _upsert_report_index(self, report: dict[str, Any]) -> None:
        path = self.settings.data("monthly-reports/index.json")
        payload = read_json(path, {"schemaVersion": 1, "reports": []})
        reports = payload.setdefault("reports", [])
        if not isinstance(reports, list):
            raise ValueError("report index reports must be a list")
        month = str(report["month"])
        entry = {
            "id": report["id"],
            "month": month,
            "title": report["title"],
            "publishedAt": report["publishedAt"],
            "coverUrl": report.get("coverUrl", ""),
            "file": f"monthly-reports/{month}.json",
        }
        replaced = False
        for index, current in enumerate(reports):
            if isinstance(current, dict) and current.get("month") == month:
                reports[index] = entry
                replaced = True
                break
        if not replaced:
            reports.append(entry)
        reports.sort(key=lambda item: str(item.get("month", "")) if isinstance(item, dict) else "", reverse=True)
        payload["schemaVersion"] = 1
        write_json_atomic(path, payload)

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
            "report-index": "月报索引",
        }
        return labels.get(key, key.removeprefix("report:") + " 月报")


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
        server.server_close()
