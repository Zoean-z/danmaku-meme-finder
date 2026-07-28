# Current Goal

Add safe local collection controls to the existing localhost admin without creating a public collector service.

# Active Checklist

- [x] Add one in-process collection controller around the existing `run_collection()` workflow.
- [x] Expose localhost-only start, stop, and status endpoints.
- [x] Add a compact collection workspace with duration, status, imported count, and candidate result.
- [x] Keep graceful Node shutdown, final SQLite import, candidate generation, and session persistence unchanged.
- [x] Cover start conflicts, stop behavior, status, and UI controls without a real Douyu connection.
- [x] Update README and complete targeted Python, JavaScript, HTTP, and browser verification.

# Decisions

- Collection remains local-only; the public Vercel website cannot start a process on the user's computer.
- Reuse `CollectionSettings` and `run_collection()` instead of adding a second collector implementation.
- Allow only one collection job at a time and make Stop cooperative through asyncio task cancellation so the existing `finally` block flushes remaining data.
- Require the existing local meme index before starting; do not make admin startup silently perform a network sync.
- Show imported messages from SQLite while running; raw JSONL and user identifiers remain inaccessible to the browser UI.

# Blockers

- The full suite has one date-sensitive pre-existing failure: `test_collection_runner.py` uses fixed 2026-07-25 records with a 48-hour window, which no longer includes them on 2026-07-28. The production filter was not weakened for this admin change.

# Next Step

Use `python -m danmaku_meme_finder.cli admin` for the next real live collection; separately stabilize the stale date fixture before requiring a fully green suite.
