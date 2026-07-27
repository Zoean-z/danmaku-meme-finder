# Current Goal

Preserve exact collection-session provenance from raw danmaku through curated
catalog records, and make events and sessions easy to create in the local admin.

# Active Checklist

- [x] Verify the v3.2.0 README and release notes
- [x] Identify that 6657 is a VIP/short ID and verify its real rid 6979222 receives chatmsg
- [x] Add and validate automatic short-ID resolution in the project collector
- [x] Add checkpointed Python JSONL import
- [x] Remove Python WebSocket/TLS collector dependencies and update docs/tests
- [x] Run end-to-end local verification
- [x] Exclude short (<5 characters) and known activity texts from candidate output
- [x] Add optional lexical near-duplicate merging for candidate review
- [x] Define Git-tracked versus local-only data files
- [x] Initialize the local Git repository and verify local-only data is ignored
- [x] Make the first focused commit
- [x] Create, connect, and publish the public GitHub repository
- [x] Add one `collect` command to supervise Node collection, periodic SQLite import, and candidate output
- [x] Verify the new command with fixtures and a short live smoke test
- [x] Define a canonical public meme record with tags and source provenance
- [x] Add an offline merged catalog export for the website
- [x] Sync the legacy API, build the first full catalog, and publish it to GitHub
- [x] Add a local interactive candidate-review command for manual tag entry
- [x] Replace hash-style catalog IDs with stable five-digit numeric IDs and rebuild the catalog
- [x] Store public live-session snapshots and associate collected messages with a session
- [x] Backfill and publish the first observed sessions for 2026-07-24 and 2026-07-25
- [x] Add label-assisted candidate review and automatic curated-data publishing
- [x] Add a one-command collection-to-review workflow and local rejected-candidate queue
- [x] Add a static event-date table and preserve local meme observation dates for website joins
- [x] Promote events and sessions to stable website-facing JSON contracts
- [x] Add independently maintainable monthly report index and article files
- [x] Make the website load events, sessions, tags, and monthly reports from GitHub JSON
- [x] Validate the Python suite and production website build after the data migration
- [x] Define the local admin API and reuse existing review/publish behavior
- [x] Build the candidate-review and structured JSON editing interface
- [x] Add an explicit GitHub publish action and safety checks
- [x] Add tests, documentation, and a production smoke test
- [x] Measure current catalog size and date distribution
- [x] Export a manifest, a three-month active catalog, and monthly archive shards
- [x] Export a small daily trend summary so historical charts do not load archive items
- [x] Keep stable five-digit IDs and source metadata unchanged across shards
- [x] Switch the website's initial load from catalog.json to catalog/active.json
- [x] Add archive-month lazy loading and preserve 50-item client pagination
- [x] Remove the monolithic catalog after the website migration is verified
- [x] Aggregate candidate occurrences by session without duplicating public memes
- [x] Preserve session occurrences through approval and catalog sharding
- [x] Recalculate each session's meme and barrage totals during publishing
- [x] Add structured new-event and new-session actions to the local admin
- [x] Make website session pages filter by session ID with a legacy date fallback
- [x] Backfill existing local memes from SQLite where exact session evidence exists
- [x] Validate, publish data changes, and deploy the updated website

# Decisions

- Use `douyudm` v3.2.0; Python only owns local persistence and analysis.
- Keep all state local: SQLite and JSON files only.
- Keep broad candidate pools; only collapse obvious textual variants when requested.
- GitHub distributes `memes.json` and candidate snapshots only; raw data stays local.
- Raw messages remain in SQLite for repeat counting; existing-meme filtering applies to generated candidates.
- Merge the legacy API and local confirmed memes offline into one GitHub JSON snapshot; do not merge them in the browser.
- The catalog is distributed as an active snapshot plus monthly archives; retain legacy tag IDs and source metadata unchanged.
- Catalog items use stable five-digit numeric IDs; original upstream IDs remain source metadata.
- Store room metadata once per collection; date fields describe local observation, not asserted platform start time.
- Keep one public meme record per normalized text; store per-session counts and times in `collectionOccurrences`.
- Prefer exact `sessionId` joins on the website and use calendar-date matching only for legacy records without session provenance.
- Keep the tag code-to-label map as tracked JSON; review publishes only formal memes and catalog data.
- Keep rejected-candidate state local and ignored; do not delete the Git-tracked candidate snapshot after review.
- Keep event metadata in one manual date-range table; the website joins it by inclusive local calendar date.
- Keep report prose and session summaries in tracked JSON; the website renders them without inventing copy at runtime.
- Generate daily trend data during catalog export so charts and old event totals remain available without downloading archive items.
- Bind the admin server to localhost and use the standard library; do not add a public backend or database service.
- Keep candidate review as the primary workspace; expose events, sessions, reports, and tags as validated editors.
- Require an explicit click before any Git commit/push operation.
- Treat the current month plus two previous months as the maintained active set; older months become read-only archives.
- Shard archives by latest source month so every catalog item appears in exactly one file.
- Do not add page-sized files yet; monthly shards already cap normal fetches near one megabyte and keep filtering practical.

# Blockers

- The v3.2.0 CLI sends no chatmsg when given a VIP/short ID; it needs the real rid.
- None for the local-first MVP.
- Legacy tag IDs need a tag-name mapping if the website should render human-readable category labels.
- None for the current data-publishing path.

# Next Step

Use the local admin for normal event, session, report, and candidate maintenance;
new collection runs now carry exact session provenance automatically.
