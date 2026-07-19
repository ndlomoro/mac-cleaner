# Smarter Duplicates — Design (Phase 5)

**Date:** 2026-07-19
**Status:** Approved
**Phase:** 5 of the rebuild (safety ✓ → UI ✓ → dev-junk ✓ → iOS/Mail ✓ → **smarter duplicates** → orphaned app data)
**Vocabulary:** `/CONTEXT.md` binding; adds **Keeper**.

## Goal

Make the duplicates scan fast enough for media libraries and the pick flow smart enough to be quick — without weakening the nothing-pre-selected rule for user data.

## Scope decision (approved)

Suggest, never pre-select: a ★ Keeper badge per group + one keystroke selecting "all but keepers". Pre-selection rejected (would weaken the phase-1 user_data invariant).

## Scanner (`scanner/duplicates.py`)

- **Three-stage filtering:** (1) size groups (existing); (2) partial hash — first 64KB — only within multi-member size groups; (3) full hash only within multi-member partial-hash groups. Full-content hashing drops to survivors only (typically ~5% of candidates on media trees).
- **Floor raised:** `min_size_bytes` default 10KB → 1MB (duplicates below 1MB rarely matter for space; amendable constant).
- `.photoslibrary` exclusion and SKIP_EXTENSIONS retained. Group shape unchanged: `{hash, size, files, wasted}` (hash = full hash).
- **`pick_keeper(paths: list[str]) -> str`** — pure, deterministic heuristic for the copy to KEEP: prefer canonical dirs (`~/Pictures`, `~/Documents`, `~/Movies`, `~/Music`) over transient ones (`~/Downloads`, `~/Desktop`); then shortest path depth; then oldest mtime; ties broken lexicographically.

## UI (Duplicates tab, Space Finder)

- Group rows render with `★ keep` on the keeper and plain rows otherwise; groups visually contiguous (existing ordering by wasted space).
- New binding `k` ("Select duplicates"): for every group, select all NON-keeper copies — never the keeper, never anything pre-selected before the user presses it. Keep-One remains independently enforced (pressing `k` can never violate it by construction; the handler stays as the backstop).
- Everything else unchanged: ConfirmModal, user_selected=True, outcome-driven refresh, reclaim offer.

## Testing

Full-hash call counting proves stage 3 only sees partial-hash survivors; partial-collision-but-full-difference case (same first 64KB, different tails) must NOT group; keeper heuristic table-driven (canonical-vs-transient, depth, mtime, tie); pilot: `k` selects exactly non-keepers, keeper unselectable-by-k, nothing selected before k; floor test at the 1MB boundary.

## Out of scope

Cross-tab dedup awareness beyond the existing cross-tab Keep-One check; perceptual/near-duplicate matching; phase-6.
