# Current Goal

Use `douyudm` v3.2.0's current WebSocket implementation to write JSONL, then
import that local stream into the existing SQLite/candidate pipeline. Publish
only small curated JSON snapshots through GitHub.

# Active Checklist

- [x] Verify the v3.2.0 README and release notes
- [x] Identify that 6657 is a VIP/short ID and verify its real rid 6979222 receives chatmsg
- [x] Add and validate automatic short-ID resolution in the project collector
- [x] Add checkpointed Python JSONL import
- [x] Remove Python WebSocket/TLS collector dependencies and update docs/tests
- [x] Run end-to-end local verification
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

# Decisions

- Use `douyudm` v3.2.0; Python only owns local persistence and analysis.
- Keep all state local: SQLite and JSON files only.
- Keep broad candidate pools; only collapse obvious textual variants when requested.
- GitHub distributes `memes.json` and candidate snapshots only; raw data stays local.
- Raw messages remain in SQLite for repeat counting; existing-meme filtering applies to generated candidates.
- Merge the legacy API and local confirmed memes offline into one GitHub JSON snapshot; do not merge them in the browser.
- The first catalog is a single full snapshot; retain legacy tag IDs even without a label map.
- Catalog items use stable text-derived IDs; original upstream IDs remain source metadata.

# Blockers

- The v3.2.0 CLI sends no chatmsg when given a VIP/short ID; it needs the real rid.
- None for the local-first MVP.
- Legacy tag IDs need a tag-name mapping if the website should render human-readable category labels.
- None for the current data-publishing path.

# Next Step

Point the website at `data/catalog.json`; if its initial 10.6 MB load is too slow,
split the catalog into a manifest and static shards without changing item format.
Implement the website's catalog reader and first browse/search view against the
published stable-ID schema.
