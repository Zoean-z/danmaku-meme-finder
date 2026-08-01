# Status

## 2026-07-31 - Public trend and archive correction

- `data/trends/daily.json` schema v2 now contains only measured collector volume from `sessions.json`; legacy API `cnt` copy popularity is no longer treated as a barrage count.
- The three measured dates total 52,811 collected messages (3,694 + 10,637 + 38,480), exactly matching the session records.
- `catalog/search-index.json` now includes compact `sourceKinds`; 68 of 21,671 current records are positively identified as local self-captures.
- `events.json` contains 11 major events from IEM Kraków 2026 through BLAST Bounty 2026 Season 2.
- Empty monthly-report documents and their obsolete admin creation flow were removed from the public data set.
- Catalog generation now requires session metadata for trend output; CLI review and localhost admin publishing pass it through.
- Verification: 45 Python tests pass after removing two obsolete monthly-report tests; package compilation, JavaScript syntax, and `git diff --check` pass.

The existing API index is synced locally and the SQLite/candidate workflow is
retained. Python no longer owns a Douyu connection layer. An earlier short probe
of `douyudm` reached its server but received no `chatmsg`, even while room 6657
was visibly live; its `live_stat=0` must not be treated as room status. The
project uses the current GitHub v3.2.0 release, whose official recorder includes
automatic port retry. A 55-second official CLI `--record` probe against the live
room wrote only its JSONL metadata header (1 line, 79 bytes) and no `chatmsg`.
The same 55-second comparison probe against room 601514 also produced only its
metadata header (1 line, 81 bytes) and no `chatmsg`.
Source inspection shows that retry applies only before a WebSocket opens; the
library still uses the old `danmuproxy.douyu.com:8501-8506` STT route and joins
group `-9999`. `import-jsonl` remains ready, but collecting current 6657 chat
requires either browser DOM capture (validated as readable) or a separate Tencent
IM protocol implementation.

An additional protocol experiment delayed `joingroup` until `loginres`. This
made room 601514 emit `uenter` events, suggesting a timing sensitivity, but it
still produced no `chatmsg`; room 6657 then emitted only `loginres`, `pingreq`,
`mrkl`, `dream_bus_session`, and `defense_tower_session`. The simple join-order
change is therefore insufficient to restore normal chat collection.

The actual fix is resolving the configured VIP/short room ID before connecting:
the mobile page for 6657 contains `rid=6979222` and `vipId=6657`. A 45-second
collector run with `Client(6979222)` received and wrote more than 60 `chatmsg`
records. The collector now resolves this real rid automatically while preserving
the configured room ID in exported and stored records.

The earlier comparison room 601514 is a real rid, but its mobile page currently
identifies it as a replay; its lack of normal chat is not evidence that the STT
protocol is globally broken. The confirmed project failure and fix are specific
to passing 6657's VIP/short ID instead of its real rid 6979222.

End-to-end validation completed: importing `data/live.jsonl` wrote 69 records
to SQLite, with 38 unique texts in the last 24 hours. Candidate generation then
wrote 10 candidates. Node syntax validation and all 11 Python tests pass.

Candidate output now excludes normalized texts shorter than five characters and
the known Douyu activity text `保卫鱼娘`. The candidate JSON records per-rule
exclusion counts. Existing-meme exclusion still depends on refreshing
`data/existing_index.json`; the local `data/memes.json` currently contains no
entries.

Candidate generation also checks confirmed entries in `data/memes.json` in
addition to the refreshed external index, so locally reviewed memes no longer
reappear as candidates.

Follow-up collection validation wrote 3,625 additional JSONL records and imported
them successfully, for 3,694 local messages and 1,029 unique texts in the
24-hour window. Candidate review should retain a broad pool: using `min-count=20`
produced 171 candidates (36 high-frequency and 135 single-occurrence long texts),
many of which are useful meme candidates despite being event-specific or remixed.
The optional `--similarity-threshold 0.88` mode now merges only obvious lexical
variants while retaining their source records under `similarVariants`; the same
input became 141 representatives with 30 variants merged. All 12 tests and an
import check pass after this change.

GitHub publishing preparation is in place: raw JSONL, SQLite, import checkpoints,
the external API cache, and threshold experiments are ignored. Only the code,
README, `data/memes.json`, and current candidate snapshots are intended for a
future repository. This directory is not yet a Git repository and has no remote.

The local Git repository has now been initialized on `main`. GitHub CLI
authentication is available, and `.gitignore` has been checked against the raw
database, JSONL, external index cache, and threshold comparison outputs. No
remote, commit, or GitHub repository has been created yet.

The initial public repository is now published at
`https://github.com/Zoean-z/danmaku-meme-finder` on the `main` branch. Its
initial commit contains only the intended project code, documentation, curated
JSON snapshots, and data policy; raw collection data remains untracked locally.

The next workflow improvement is a single local `collect` CLI command. It will
supervise the Node collector, periodically import its JSONL output into SQLite,
and refresh a candidate file that already excludes the existing meme index.
Raw messages will remain local because repeat counts require them; the existing
index is used to filter candidate output rather than discard collection evidence.

The `collect` command is implemented and verified. It starts the Node supervisor,
imports complete JSONL records into SQLite every five seconds by default, and on
stop performs a final import plus candidate build. A live eight-second smoke test
resolved 6657 to 6979222, imported one newly received message, and refreshed
`data/candidates.json`; the fixture suite now has 13 passing tests.

Website data is now the next design focus. The recommended path is an offline
merged catalog with one canonical record format, committed to GitHub for static
reads. It should preserve legacy API tags and source IDs, retain local confirmed
memes, and avoid adding counts from different sources together.

The first real legacy sync on 2026-07-25 fetched 22,024 API records and reduced
them to 21,603 normalized texts. `build-catalog` exported the matching static
catalog successfully; the first full snapshot is about 10.6 MB, so it validates
the one-file website path but may later need static sharding for faster loads.
The catalog and its exporter are published on GitHub commit `6931d3c`; the website
can now read only the GitHub raw `data/catalog.json` file and does not need to
contact the legacy API at runtime.
Catalog records now include a stable unified `id`; legacy and local source IDs
remain separately available as `sources[].sourceId`.
The hash-style unified-ID commit `699840a` is published on GitHub. It is now
being replaced with stable five-digit display IDs plus a local interactive
candidate-review command for manual tag entry. Websites should continue to use
the top-level `id` as canonical and treat `sources[].sourceId` as provenance.

The replacement is implemented and validated locally: `review-candidates`
accepts comma-separated tag IDs, skips on an empty line, and saves each
accepted candidate atomically. The rebuilt schema-version-2 catalog contains
21,603 unique five-digit IDs. This pending catalog update still needs a GitHub
push before a website can consume the new numeric ID format.

The next data addition is a small public `sessions.json`: one metadata snapshot
per collection, with a best-effort Douyu title/category/cover URL and explicit
local observation times. Raw danmaku remains local, but its SQLite rows will be
associated with a session ID for per-live candidate context.

Live-session storage is now implemented and validated. The collector obtains a
best-effort public room snapshot before each run, writes a session ID into new
JSONL/SQLite records, and closes the session with its message count. The first
two observed snapshots are backfilled: 3,694 messages on 2026-07-24 and one
message on 2026-07-25. `sessions.json` is public and stores only room metadata,
observation times, counts, and an external Douyu CDN cover URL.

Label-assisted review is implemented: `data/tags.json` mirrors the website tag
map, `review-candidates` accepts codes or labels and `?` displays the menu. On
completion it atomically updates the formal meme files, commits only those two
public JSON files, and pushes the current branch. Candidate defaults are now
100 entries; short texts and known activity text are excluded before review.

The streamlined workflow now includes `collect-and-review`: it collects until
`Ctrl+C` (or `--duration`), performs the existing final import and candidate
build, then starts review. Each candidate shows the full tag catalog. `x` or
`n` records a local rejection in ignored `data/review_state.json`; confirmed and
rejected normalized texts are removed from future review queues without deleting
the Git-tracked candidate snapshot. Confirmed records continue to auto-publish
only `memes.json` and `catalog.json`.

Public tournament context is stored separately in `data/events.json`. Each event
has an inclusive `beginDate` / `endDate` range, named teams, a display stream
title, and an optional reusable cover URL. Local formal memes now retain their
candidate `firstSeenAt` / `lastSeenAt` values and catalog local sources expose
those fields, so the website can associate a date with an event without copying
tournament metadata into raw danmaku.

The public presentation data is being promoted from runtime derivation to stable
JSON contracts. `events.json` now uses `title`, `startDate`, `endDate`, and a
local cover path while retaining optional event details. `sessions.json` adds a
calendar date, editorial summary, and explicit meme/barrage counts without
discarding collector observation metadata. Monthly report index and article
files for May through July 2026 are tracked separately so copy can be maintained
without changing frontend code. Daily trends remain derived from `catalog.json`
for now.

The matching website adapter now loads the four presentation datasets directly
from GitHub, and the former hardcoded event table and runtime monthly-article
generator have been removed. Existing site artwork is copied into stable event,
session, and report cover paths so each JSON record can be updated independently.
The Python suite passes all 26 tests, the package compiles, and the website
production build succeeds after the migration.

The next project direction is a localhost-only management workspace. It will
reuse the existing candidate review, atomic JSON writing, catalog building, and
Git publishing code while adding a browser UI for high-volume review and manual
maintenance of events, sessions, tags, and monthly reports. This is an operator
tool, not a public service or replacement for SQLite/CLI collection.

The local management workspace is implemented under the `admin` CLI command.
It provides a dense candidate-review surface with complete tag selection,
approve/reject/skip actions and keyboard shortcuts; a central validated editor
for events, sessions, tags, formal memes, and monthly reports; automatic monthly
index maintenance; and an explicit publish action that rebuilds the catalog and
pushes only named public files. It binds only to `127.0.0.1`, never exposes raw
JSONL or SQLite data, and requires a current local existing-index cache before
publishing. The suite now has 31 passing tests, the localhost HTTP smoke test
returns the real 100-item queue and eight managed documents, JavaScript syntax
passes, the wheel contains all three admin assets, and both review/content views
were checked in a real browser without console errors.

Catalog performance was measured before starting a migration. The current
`catalog.json` has 21,603 items and is 10.66 MiB uncompressed (1.97 MiB gzip),
and the website currently downloads and parses all of it before slicing a
50-item page in memory. Every record has a usable source date. Keeping May,
June, and July 2026 active would retain 2,498 items at roughly 0.9 MiB raw;
the remaining 20 months can be immutable monthly shards. The recommended next
step is therefore active-plus-monthly-archive lazy loading, not merely visual
pagination over the same monolithic download.

The catalog migration is complete and published. `data/catalog/manifest.json`
now describes a 2,498-item active set for May through July 2026 and 20 immutable
monthly archive shards containing the other 19,105 items. The former 10.66 MiB
`data/catalog.json` monolith has been removed. A 617-point daily trend summary
keeps historical charts and event totals available without loading archived
records. The website loads only the active catalog initially, fetches an archive
month when an old date or event requests it, and retains 50-item client pages.
All 33 Python tests, package import compilation, and the website production
build pass; Sites version 6 is deployed in production.

Session provenance now remains exact after raw storage. Candidate records carry
per-session `collectionOccurrences`; approval preserves them in `memes.json`,
catalog local sources expose them, and publishing recalculates session meme,
tag, and raw barrage totals. The missing 2026-07-25 evening collection session
was reconstructed from its SQLite time range: 10,637 previously unassigned rows
now belong to `6657-20260725-184645`. All 54 current local memes have exact
session provenance; the earlier 2026-07-24 session contains five of them.
The local admin now has guided new-event and new-session actions in addition to
new monthly reports, with duplicate-ID and calendar-date validation. Website
session views use the exact session ID and retain date fallback only for legacy
API records that cannot have local session provenance. Unchanged historical
catalog shards are no longer rewritten solely because the export timestamp
changed. The Python suite now has 38 passing tests and the updated website
production build succeeds.
The session-aware data is published on GitHub and Sites version 7 is live. A
production HTTP check returned 200; the deployed JavaScript contains the exact
session filter, and the public session/catalog JSON exposes the reconstructed
evening session ID.

Full-library discovery is restored without bringing back the monolithic initial
download. Each local catalog publish now writes a 100-item `catalog/hot.json`
from all 21,657 records and an on-demand compact `catalog/search-index.json`.
The restored ranking starts with the same historical leaders as the former full
catalog. The website labels its three-month view as recent content and provides
separate hot-ranking and historical-library navigation. All 39 Python tests,
package compilation, diff checks, and the website production build pass.

Manual review is now capped at 20 candidates across `build-candidates`,
`collect`, and `collect-and-review`. Lexical near-duplicate clustering is on by
default at 0.82, ignores mention prefixes and decorative suffixes, rejects
activity/control copy, and filters variants of existing, confirmed, or locally
rejected texts before applying the cap. Similar families retain one ranked
representative plus `similarVariants` and `familyCount`. The current 48-hour
snapshot was rebuilt to 20 items: 98 existing-library variants and 208 reviewed
variants were filtered, while 46 same-batch variants were merged. All 44 tests,
package compilation, and diff checks pass.

The localhost admin now includes a dedicated collection workspace. It can start
one existing Node/Python collection workflow, accept a minute duration or run
until stopped, poll the current session and SQLite import count, and request a
graceful stop that preserves the runner's final import, candidate generation,
and session close behavior. The browser never receives raw JSONL, SQLite rows,
or user identifiers, and the public Vercel site cannot control this local task.

Collection-controller and admin UI tests pass (10 tests), Python compilation and
JavaScript syntax checks pass, the localhost HTTP UI loads real state, and the
390px layout has no horizontal overflow. The full 47-test suite currently has
one unrelated time-sensitive failure because a legacy fixture fixes messages at
2026-07-25 while querying only the latest 48 hours on 2026-07-28.

The localhost review/publish flow now owns raw-data retirement. Publishing is
blocked until the current candidate queue is empty, collection is idle, and the
JSONL checkpoint equals the file size. After the public Git push succeeds, the
admin derives explicit session IDs from candidate provenance, removes only those
rows from SQLite and JSONL, rewrites the checkpoint, and restores the original
JSONL from a temporary backup if cleanup fails. The UI warns about this boundary
before confirmation and reports the cleanup count. Cleanup/admin focused tests,
Python compilation, JavaScript syntax, diff checks, and all 49 Python tests pass.

Repeated candidates were traced to two separate behaviors: repeated messages across
collection sessions are valid raw evidence, while historical rejection previously used
one ambiguous near-match rule that missed numeric and template substitutions. Review now
has separate exact-reject and permanent-family-block actions; the latter persists
`excludeSimilar: true` and filters numeric or stable-prefix/suffix variants in later
candidate builds. Candidate source is no longer shown as a review category. The companion
website adapter also no longer turns `official`, `high_frequency`, or `long_text` provenance
into tags. All 54 Python tests pass and the website production build succeeds.

The review/cleanup changes are pushed to GitHub. The companion site is deployed as Sites
version 11 and to the Vercel production alias `6657up.zoean.xyz`; both production HTML,
JavaScript, and `api/data/tags.json` return HTTP 200, and neither built bundle contains the
three removed pseudo-category labels. The localhost admin was restarted on port 8765 and
passed desktop DOM, 390px overflow, and console-error checks.

The session-archive duplication shown for meme `#22073` was not a duplicate catalog row.
Its later raw occurrences had been counted as membership in the July 30 and July 31 archive
sessions, which also replaced its displayed heat with the per-session counts 1 and 2.
Session summaries now assign every accepted meme only to its earliest exact collection
session while retaining all occurrence evidence. Rebuilding the public data reduced the
July 30 session from 24 to 15 unique memes and July 31 from 22 to 9; all four session counts
now total exactly the 78 accepted memes, with no cross-session duplication.

The corrected data is pushed and the companion frontend is deployed only to Vercel, as
requested. Production verification shows 15 rows for July 30 and 9 for July 31, with
`#22073` absent from both. Its earliest July 25 session contains exactly one row with heat
58. The production category controls have no fixed height or internal overflow; the shared
selectors wrap all tags, and the 390px page has no horizontal overflow.
