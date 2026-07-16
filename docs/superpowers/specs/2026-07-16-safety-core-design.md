# Safety Core — Design

**Date:** 2026-07-16
**Status:** Approved
**Phase:** 1 of the "best mac cleaner" program (safety core → Textual UI → dev-junk scanner → iOS backups/mail → smarter duplicates → orphaned app data)

## Goal

Make deletion trustworthy. One engine owns every destructive action: Trash-only deletion, a hardened protected-path check with explainable skips, and a per-category safety registry (level + plain-English explanation) that the UI surfaces. Irreversible actions must declare themselves and receive stricter confirmation.

## Context

The codebase already uses `send2trash` for file deletion, but:

- `is_safe_to_delete()` (utils/helpers.py) protects only 7 system dirs; nothing protects `~/Documents`, Keychains, Photos libraries, Mail data, or running-browser profiles. Matching uses `startswith` (no component boundaries) on the resolved path.
- The delete loop is copy-pasted across 4 cleaners (`system_data`, `privacy`, `app_remnants`, `optimization`) with drift.
- Protected-path skips are silent (`continue`), invisible to the user.
- No category carries a safety level or explanation.
- Snapshots (`tmutil` + sudo) and recents-clearing (in-place file overwrite) bypass Trash and are silently non-undoable.

## Architecture

New package `core/` owns all deletion decisions:

```
core/
├── safety.py      # ProtectedPaths: is_protected(path) -> (bool, reason)
├── registry.py    # Category registry: SAFE/CAUTION/RISKY + explanation per category
└── deleter.py     # safe_delete(paths, category, dry_run) -> DeleteReport
```

**Data flow:** scanner finds items (unchanged) → UI shows items with the category's safety level and explanation → cleaner calls `core.deleter.safe_delete(paths, category=..., dry_run=...)` → deleter checks each path against `safety.py`, sends survivors to Trash, returns a `DeleteReport`.

**Contract:** `safe_delete` is the only function in the codebase allowed to destroy data. The 4 existing cleaners shrink to thin orchestration over it. Skips are reported with reasons, never silent.

### DeleteReport

Per-path outcomes, exactly one of: `deleted`, `skipped(reason)`, `failed(error)`. Aggregates: counts and `freed_bytes`. Dry-run returns the identical shape with nothing touched, so preview and real runs share one UI code path.

## Protected paths (core/safety.py)

Checked in order on the **resolved** path (symlink-safe), with proper path-component boundary matching (`/Systemwide` is not protected; `/System/x` is).

1. **System-critical (never touch):** `/System`, `/bin`, `/sbin`, `/usr` (except `/usr/local`), `/private/var/db`, `/Library/Apple`, boot volume roots.
2. **User-data (never touch):** `~/Documents`, `~/Desktop`, `~/Pictures`, any `*.photoslibrary`, `~/Library/Keychains`, `~/Library/Mail` (mailboxes, not caches), `~/.ssh`, `~/.gnupg`, iCloud Drive root, the Trash itself.
3. **Conditional:** a browser's profile dir while that browser is running (`pgrep`); any path modified in the last 10 minutes (in-use heuristic).

`is_protected(path)` returns `(True, "reason string")` so the UI can explain skips (e.g. "Skipped: Chrome is running").

## Safety registry (core/registry.py)

Every cleanable category declares:

| Field | Meaning |
|---|---|
| `key` | e.g. `browser_cache` |
| `level` | `SAFE` / `CAUTION` / `RISKY` |
| `explanation` | One plain-English line: what it is, consequence of removal |
| `irreversible` | `True` only for non-Trash actions (snapshots, recents-clear) |

Initial assignments:

- **SAFE:** user caches, logs, temp files, browser caches, dev caches (Xcode DerivedData, CocoaPods, npm, pip), brew cleanup.
- **CAUTION:** app leftovers, launch agents (explanation names the owning app).
- **RISKY:** browser history/tracking data; snapshots and recents-clear additionally `irreversible=True`.

`safe_delete` refuses any category not in the registry — future scanners must declare a level and explanation before they can delete anything.

## Irreversible actions

`snapshots.py` and `clear_recently_used` keep their own mechanisms (tmutil / in-place overwrite) but consult the registry; the UI layer must show a distinct red warning and type-to-confirm ("yes") before invoking anything with `irreversible=True`. Dry-run remains available.

## Error handling

- `safe_delete` never raises for a single bad path; every path lands in the report.
- Trash failure (including ENOSPC) → `failed` with a human message suggesting Empty Trash. Never falls back to permanent delete.
- Unknown category → refuse the whole call (programming error, not user error).

## Testing (TDD, pytest)

- `tests/test_safety.py` — table-driven protected-path cases per tier; symlink-escape attempts (symlink inside a cache dir pointing at `~/Documents` must be caught); component-boundary cases.
- `tests/test_deleter.py` — tmp-dir fixtures; deletes route to Trash (mock `send2trash`); skips carry reasons; report math adds up; unknown category refuses; dry-run leaves files untouched.
- `tests/test_registry.py` — every category referenced by any cleaner exists; every entry has a non-empty explanation.
- Existing cleaner tests updated to assert delegation to `safe_delete`.

## Out of scope (this phase)

- Textual UI (phase 2 consumes registry levels/explanations).
- New scanners (dev junk, iOS backups, mail, orphaned data) — they inherit safety for free.
- Deletion-history manifest / vault — Trash-only per decision; the `safe_delete` contract allows adding a manifest later without changing callers.
