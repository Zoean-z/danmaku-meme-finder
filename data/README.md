# Data policy

Tracked in GitHub:

- `memes.json`: the small, manually curated public meme library.
- `candidates.json`: the current candidate snapshot for review.
- `candidates-deduplicated.json`: an optional current snapshot that collapses obvious text variants while retaining them in `similarVariants`.
- `catalog.json`: the static website catalog merged from the legacy index and local confirmed memes.
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
