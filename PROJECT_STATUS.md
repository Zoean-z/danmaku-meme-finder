# Status

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
