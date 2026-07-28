# Progress

## 2026-07-28 - Local admin collection controls

- Added a localhost-only collection workspace with duration, start, graceful stop, session ID, SQLite import count, and candidate count.
- Reused the existing `CollectionSettings` and `run_collection()` path; no second collector implementation or public service was introduced.
- Added local start, stop, and status endpoints with a single-active-task guard.
- Added fixture coverage for start conflicts, cooperative cancellation, missing existing index, and UI controls.
- Verified 10 admin tests, Python compilation, JavaScript syntax, localhost HTTP rendering, and a 390px browser layout without horizontal overflow.
- Full-suite verification exposed one unrelated stale-date fixture in `tests/test_collection_runner.py`; production time-window logic was left unchanged.

### decision_audit

- Modified `.project-loop/PLAN.md`, `PROJECT_STATUS.md`, `progress.md`, `README.md`, `src/danmaku_meme_finder/admin.py`, the three `admin_static` assets, and `tests/test_admin.py`.
- The controller maps to local collection orchestration; HTTP routes map to localhost control; static assets map to operator UI; tests and docs map to the acceptance and privacy constraints.
- Stop uses asyncio task cancellation because the existing runner already guarantees Node termination, final JSONL import, candidate generation, and session closing in `finally`.
- The UI reports only aggregate state and never exposes JSONL, SQLite rows, nicknames, or raw user identifiers.
- No public server, Vercel control endpoint, new dependency, collector protocol change, or automatic Git publish was added.
- Next step is one real collection launched manually from the admin when the room is live.
