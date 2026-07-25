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
- [ ] Make the first focused commit
- [ ] Create and connect a GitHub repository

# Decisions

- Use `douyudm` v3.2.0; Python only owns local persistence and analysis.
- Keep all state local: SQLite and JSON files only.
- Keep broad candidate pools; only collapse obvious textual variants when requested.
- GitHub distributes `memes.json` and candidate snapshots only; raw data stays local.

# Blockers

- The v3.2.0 CLI sends no chatmsg when given a VIP/short ID; it needs the real rid.
- A GitHub repository name and visibility have not been chosen.

# Next Step

Initialize Git locally, then create a GitHub remote and publish the small
read-only JSON artifacts without raw collection data.
