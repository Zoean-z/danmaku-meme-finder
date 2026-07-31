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

## 2026-07-31 - Measured public trends and provenance

- Replaced catalog-derived trend generation with session-derived barrage totals; dates without a measured session no longer get a point.
- Added `sourceKinds` to the compact search index so the website history view can show the same positive `自采` marker as active shards.
- Rebuilt 21,671 catalog records and verified 68 local-source records in the search index.
- Replaced the stale event list with 11 major 2026 events from IEM Kraków through BLAST Bounty Season 2.
- Removed the empty monthly-report JSON documents from the public data set.
- Removed the admin dashboard's monthly-report counter, editor documents, and creation action so it cannot recreate unpublished orphan files.
- Updated the stale fixed-date collection test without weakening the production 48-hour filter.
- Verification: focused catalog tests 6/6; after removing two obsolete monthly-report tests, the full Python suite passes 45/45, package compile and CLI import check passed.

### decision_audit

- Modified catalog generation, CLI/admin call sites, catalog tests, the stale test fixture, public catalog/trend/event JSON, and project status files.
- Legacy API `cnt` is retained only as copy popularity inside catalog sources; it is not converted, estimated, or relabeled as a collected message count.
- Session totals are the sole trend source. The generated 52,811-message total exactly equals `sessions.json`.
- Event counters remain derived at website runtime from measured sessions; adding editorial event dates does not fabricate historical counts.
- `data/candidates.json`, raw JSONL, SQLite, checkpoints, and user identifiers were not changed.
