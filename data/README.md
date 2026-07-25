# Data policy

Tracked in GitHub:

- `memes.json`: the small, manually curated public meme library.
- `candidates.json`: the current candidate snapshot for review.
- `candidates-deduplicated.json`: an optional current snapshot that collapses obvious text variants while retaining them in `similarVariants`.
- `catalog.json`: the static website catalog merged from the legacy index and local confirmed memes.

Local only and ignored by Git:

- `danmaku.db` and `live.jsonl`: raw collection data.
- `live.import.checkpoint.json`: local JSONL import state.
- `existing_index.json`: a regenerable cache of the external meme API.
- `candidates-min*.json`: one-off threshold comparison outputs.

GitHub is the read-only distribution layer for the small curated JSON files, not
the raw danmaku archive.
