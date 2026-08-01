# Current Goal

Prevent reviewed meme families from returning as candidates, and remove source-derived pseudo-categories from the review and public website.

# Active Checklist

- [x] Diagnose repeated raw messages versus repeated review candidates.
- [x] Split exact rejection from permanent similar-family blocking.
- [x] Add the permanent-block action to browser and CLI review flows.
- [x] Remove candidate-source labels from the admin review UI.
- [x] Stop the website adapter from generating source pseudo-tags.
- [x] Publish both repositories and verify the deployed admin/site behavior.

# Decisions

- Ordinary rejection remains exact so reviewers do not accidentally suppress a broad family.
- The explicit permanent-block action stores `excludeSimilar: true` in ignored local review state.
- Similar-family matching additionally handles numeric variants and template phrases with a stable prefix or suffix.
- `official`, `high_frequency`, and `long_text` remain internal provenance values, never user-facing tags.

# Blockers

- None currently.

# Next Step

Use the new permanent-family action during future reviews when a template should never return.
