# Current Goal

Correct the public archive metadata so the website only presents measured collection counts, exposes self-captured provenance in the full history index, and carries a current six-month major-event calendar.

# Active Checklist

- [x] Build `trends/daily.json` only from real `sessions.json` barrage totals.
- [x] Add source kinds to the compact search index so `/history` can show `自采`.
- [x] Replace stale event metadata with the latest six months of major CS2 events through BLAST Bounty 2026 Season 2.
- [x] Regenerate public catalog/trend files without touching raw local data or the pending candidate file.
- [x] Remove empty monthly-report data and the obsolete admin creation flow.
- [x] Add regression tests and run the focused/full Python suites.

# Decisions

- Legacy API `cnt` remains copy popularity and must never be relabeled as a collected barrage count.
- Daily trend points aggregate `sessions[].barrageCount` and `sessions[].messageCount`; dates without a local session have no point.
- Compact history records carry only a small `sourceKinds` list, not full source metadata.
- Event dates are editorial metadata; event counters are still computed only from locally measured sessions.

# Blockers

- None currently.

# Next Step

Commit/publish the verified data and website changes when requested.
