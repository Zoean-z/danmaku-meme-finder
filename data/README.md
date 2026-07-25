# Data policy

Tracked in GitHub:

- `memes.json`: the small, manually curated public meme library.
- `candidates.json`: the current candidate snapshot for review.
- `candidates-deduplicated.json`: an optional current snapshot that collapses obvious text variants while retaining them in `similarVariants`.
- `catalog.json`: the static website catalog merged from the legacy index and local confirmed memes.
- `sessions.json`: public live-session snapshots with metadata and a Douyu CDN cover URL.
- `tags.json`: the public code-to-label tag catalog used by local review and the website.
- `events.json`: manually maintained tournament date ranges, teams, display title, and reusable cover URL.

Local only and ignored by Git:

- `danmaku.db` and `live.jsonl`: raw collection data.
- `live.import.checkpoint.json`: local JSONL import state.
- `existing_index.json`: a regenerable cache of the external meme API.
- `review_state.json`: local-only rejected-candidate decisions, kept out of Git and the next review queue.
- `candidates-min*.json`: one-off threshold comparison outputs.

GitHub is the read-only distribution layer for the small curated JSON files, not
the raw danmaku archive.

`events.json` uses inclusive `beginDate` / `endDate` values in the
`Asia/Shanghai` calendar. The website associates a session's observation date,
or a local meme source's `firstSeenAt` / `lastSeenAt`, with the matching event;
raw danmaku rows do not duplicate event metadata.
