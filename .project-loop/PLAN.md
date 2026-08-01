# Current Goal

Keep collection-session archives unique and make every category selector fully visible without scrolling.

# Active Checklist

- [x] Trace duplicate session rows to later occurrences being treated as new collection membership.
- [x] Keep all occurrence evidence but assign each accepted meme to its earliest collection session.
- [x] Recalculate session counts and category summaries without repeated meme IDs.
- [x] Preserve aggregate heat in the full catalog and use first-session heat in session views.
- [x] Remove the height cap and scroll behavior from all shared category selectors.
- [ ] Publish data and code, deploy Vercel only, and verify the production routes.

# Decisions

- Repeated occurrences remain attached to a meme for evidence and total heat.
- A meme belongs to exactly one archive session: its earliest exact `collectionOccurrence`.
- Session heat uses that canonical occurrence count; unfiltered catalog heat uses the sum of all occurrences.
- Category controls wrap to as many lines as needed and never create an internal scrollbar.

# Blockers

- None currently.

# Next Step

Deploy and verify the corrected Vercel production site without updating Sites.
