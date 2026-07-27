# Data policy

Tracked in GitHub:

- `memes.json`: the small, manually curated public meme library.
- `candidates.json`: the current candidate snapshot for review.
- `candidates-deduplicated.json`: an optional current snapshot that collapses obvious text variants while retaining them in `similarVariants`.
- `catalog/manifest.json`: catalog totals plus active and archive shard metadata.
- `catalog/active.json`: the current month and two preceding months for the website's initial load.
- `catalog/hot.json`: the full-catalog top 100, recalculated only during local publishing.
- `catalog/search-index.json`: a compact, on-demand index for full-library search and history browsing.
- `catalog/archive/YYYY-MM.json`: immutable older records grouped by latest source month.
- `trends/daily.json`: small precomputed historical totals for charts and event summaries.
- `sessions.json`: public live-session snapshots with presentation fields, counts, and collector observation metadata.
- `tags.json`: the public code-to-label tag catalog used by local review and the website.
- `events.json`: manually maintained tournament date ranges and website cover paths.
- `monthly-reports/index.json`: ordered list of published monthly report documents.
- `monthly-reports/YYYY-MM.json`: manually maintained monthly article content and summary metrics.

Local only and ignored by Git:

- `danmaku.db` and `live.jsonl`: raw collection data.
- `live.import.checkpoint.json`: local JSONL import state.
- `existing_index.json`: a regenerable cache of the external meme API.
- `review_state.json`: local-only rejected-candidate decisions, kept out of Git and the next review queue.
- `candidates-min*.json`: one-off threshold comparison outputs.

GitHub is the read-only distribution layer for the small curated JSON files, not
the raw danmaku archive.

`events.json` uses inclusive `startDate` / `endDate` values in the
`Asia/Shanghai` calendar. The website associates a session's observation date,
or a local meme source's `firstSeenAt` / `lastSeenAt`, with the matching event;
raw danmaku rows do not duplicate event metadata.

Cover files live in the website repository under `public/covers/`; the JSON
stores root-relative URLs such as `/covers/sessions/2026-07-24.png`.
