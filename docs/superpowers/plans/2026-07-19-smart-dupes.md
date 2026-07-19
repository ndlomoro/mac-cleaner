# Smarter Duplicates Implementation Plan (Phase 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three-stage duplicate detection (size → 64KB partial hash → full hash), 1MB floor, ★ Keeper suggestions with a one-keystroke non-keeper select — nothing pre-selected, ever.

**Spec:** `docs/superpowers/specs/2026-07-19-smart-dupes-design.md`. **Vocabulary:** `/CONTEXT.md` (+ Keeper).

## Global Constraints

- All phases 1-4 contracts binding (safety, conventions, tmp_path-only tests, `.content`, no `_running`).
- Group output shape unchanged (`{hash, size, files, wasted}` — full hash); Space Finder's existing keying untouched.
- The `k` action must be provably unable to select a keeper or violate Keep-One.
- Baseline: 243 passed.

---

### Task 1: Three-stage hashing + 1MB floor (`scanner/duplicates.py`)

**Interfaces:** `find_duplicates(min_size_bytes=1_000_000)`; internal `_partial_hash(path, length=65536)`; full `_file_hash` unchanged. Stage 2 groups by (size, partial); stage 3 full-hashes only multi-member stage-2 groups.

- [ ] **RED:** tests in `tests/test_duplicates.py` (extend/replace existing): (a) monkeypatch-count `_file_hash` calls — tree with 3 same-size files where only 2 share the first 64KB → full hash called exactly twice (the stage-2 survivors), not 3×; (b) same-64KB-prefix-different-tail files do NOT group (build with a shared 64KB prefix + divergent tails); (c) 1MB floor boundary (999_999-byte duplicates ignored; 1_000_000-byte found); (d) existing group-shape/wasted assertions stay green (sizes in fixtures must grow ≥1MB or pass an explicit lower min_size_bytes).
- [ ] **GREEN:** implement stages; partial hash reads exactly the first 64KB (`f.read(65536)` once, md5); permission errors skip the file (both stages).
- [ ] Full suite; commit: `perf: three-stage duplicate detection; 1MB floor`

### Task 2: `pick_keeper` heuristic

**Interfaces:** `pick_keeper(paths: list[str]) -> str` in scanner/duplicates.py — pure. Ordering: canonical-dir membership (`~/Pictures`, `~/Documents`, `~/Movies`, `~/Music` — module const CANONICAL_DIRS, monkeypatchable) beats non-membership; then fewer path components; then oldest mtime (`file_age_days` — larger = older = preferred); then lexicographic. Missing files: treat mtime age as 0 (never crash).

- [ ] **RED:** table-driven tests: canonical beats Downloads; equal-membership → shallower path wins; equal depth → older mtime wins; full tie → lexicographic; missing file doesn't raise.
- [ ] **GREEN** + full suite; commit: `feat: pick_keeper heuristic (canonical dir > depth > age > name)`

### Task 3: ★ badges + `k` binding (Space Finder duplicates tab)

**Interfaces:** `_fill` labels duplicates rows via `_row_label` gaining a keeper marker: rows where `item["path"] == item["keeper"]` render `"★ keep  "` prefix (compute keeper per group once in `_scan`'s duplicates assembly: `keeper = pick_keeper(group["files"])`, stored on every item dict of that group). New binding `("k", "select_dupes", "Select duplicates")`: `action_select_dupes` iterates `self.items["duplicates"]`, calls `sel.select(i)` for every index whose item path != its keeper; keeper indexes never selected; respects busy guard.

- [ ] **RED:** pilot tests: (a) after scan, nothing selected; press `k` → exactly the non-keeper indexes selected, keeper not; (b) `k` then `t` → confirm flow works and keepers survive on disk (fake_trash); (c) `k` with zero duplicate groups → notify "No duplicates found." and nothing else; (d) existing Keep-One handler still fires if the user manually tries to select the keeper afterward (no regression — existing test suffices, verify).
- [ ] **GREEN** + full suite; commit: `feat: Keeper badges + one-keystroke non-keeper selection`

### Task 4: Verification + docs

- [ ] Full suite; phase-4 invariant grep set (unchanged expectations); CONTEXT.md gains **Keeper** ("The copy of a duplicate group the app suggests keeping — marked ★, never auto-selected for removal."); README duplicates section updated (three-stage speed, ★/k flow); spec-table check (duplicates row unchanged).
- [ ] Commit: `docs: Keeper vocabulary + README duplicates flow`
