# Safety Core — Design

**Date:** 2026-07-16 (revised 2026-07-17 after grilling session)
**Status:** Approved
**Phase:** 1 of the "best mac cleaner" program (safety core → Textual UI → dev-junk scanner → iOS backups/mail → smarter duplicates → orphaned app data)
**Vocabulary:** terms in bold are defined in `/CONTEXT.md` and used in their canonical sense.

## Goal

Make deletion trustworthy. One engine owns every destructive action: Trash-only deletion, a hardened protected-path check with explainable skips, and a per-category safety registry (level + plain-English explanation) that the UI surfaces. **Irreversible Actions** must declare themselves and receive stricter confirmation. The app never reports **Trashed** bytes as **Reclaimed**.

## Context

The codebase already uses `send2trash` for file deletion, but:

- `is_safe_to_delete()` (utils/helpers.py) protects only 7 system dirs; nothing protects `~/Documents`, Keychains, Photos libraries, Mail data, or running apps' caches. Matching uses `startswith` (no component boundaries).
- The delete loop is copy-pasted across 4 cleaners with drift; skips are silent.
- `scan_all()` mixes **Junk** with **Reclaimable User Data** (old Downloads, iOS backups) and `clean_system_data()` bulk-deletes all of it — including users' downloads and iPhone backups.
- Every cleaner reports `freed_bytes` for items merely moved to Trash — the number is false until Trash is emptied.
- Snapshots (`tmutil` + sudo), recents-clear (in-place overwrite), and brew/npm cleanup (external commands) bypass Trash with no distinct handling.

## Domain decisions (from grilling)

1. **Junk vs Reclaimable User Data.** Junk (regenerable byproducts) may be bulk-cleaned. Reclaimable User Data (downloads, iOS backups, large files, duplicates) must be individually and explicitly selected — never bulk-cleaned, never selected by default, regardless of age.
2. **Two axes + mechanism, not one.** `level` (SAFE/CAUTION/RISKY) is communication only. `user_data: bool` drives the bulk-clean prohibition. `via_trash: bool` records the deletion mechanism.
3. **System Data / Space Finder split.** `scan_all()` returns Junk only (`caches`, `logs`, `temp`). `downloads` and `ios_backups` move to the Space Finder area beside Large Files and Duplicates (browse → pick → confirm). Age becomes a displayed signal, never an eligibility filter (`scan_download_old`'s 90-day cutoff is removed).
4. **In Use = owner running.** A Junk path is protected while its owning app runs. Owner inference: `~/Library/Caches/<bundle-id>` names its owner; browser profile dirs map via a small explicit table; ownerless paths (`/tmp`, `/private/var/folders`) always pass. One process-list snapshot per clean run. The 10-minute-mtime heuristic is rejected (too weak on children writes, too noisy after app quit).
5. **Trashed ≠ Reclaimed.** Reports carry `trashed_bytes` (estimates from scanner sizes; no re-stat pass). "Reclaimed" is only claimed when space actually returns to disk. After a clean, the UI offers "Empty now to reclaim X" — a surgical empty that permanently deletes *only the items this app trashed this session*, never the rest of the user's Trash. Snapshot deletion reports `reclaimed_bytes` measured as the disk-free delta around `tmutil` (the tool reports nothing).
6. **Irreversible Action = RISKY and not via_trash.** Only those get the typed-"yes" gate (snapshots, recents-clear). Non-Trash SAFE categories (brew, npm) get a passive label — "cleared directly, not recoverable via Trash" — no gate, so the gate never becomes noise.
7. **Trash mechanism: PyObjC, not send2trash.** `NSFileManager.trashItemAtURL:resultingItemURL:error:` returns each item's actual Trash URL (send2trash does not), which surgical empty requires — no name-guessing inside the Trash. New dependency: `pyobjc-framework-Cocoa`. The deleter records `(original_path, trash_path, bytes)` per item.
8. **User-data tripwire.** `safe_delete` raises unless `user_selected=True` accompanies any `user_data` category. Not proof, but grep-able, review-visible, and testable. Structural backstop: the bulk path can't reach user data because `scan_all()` no longer returns it.
9. **Minimal truthful UI wiring in this phase** (no polish; Textual inherits behavior, not widgets): trashed/reclaimed wording + empty-Trash offer; level + explanation line above each category's results; skip reasons in summaries; typed-"yes" gate on Irreversible Actions; numbered pick-list for downloads/iOS backups (same pattern as the app uninstaller).

## Architecture

New package `core/` owns all deletion decisions:

```
core/
├── safety.py      # ProtectedPaths + in-use checks: is_protected(path) -> (bool, reason)
├── registry.py    # Category registry (code, dataclasses — not a config file)
└── deleter.py     # safe_delete(paths, category, dry_run, user_selected=False) -> DeleteReport
```

**Data flow:** scanner finds items (unchanged) → UI shows items with the category's safety level and explanation → cleaner calls `safe_delete` → deleter checks each path against `safety.py`, trashes survivors via NSFileManager, returns a `DeleteReport`.

**Contract:** `safe_delete` is the only function in the codebase allowed to destroy data (Irreversible Actions route their *decision* through the registry but keep their mechanisms). The 4 existing cleaners shrink to thin orchestration. Skips are reported with reasons, never silent. `utils.helpers.is_safe_to_delete` is deleted; callers migrate.

### DeleteReport

Per-path outcomes, exactly one of: `trashed(trash_path)`, `skipped(reason)`, `failed(error)`. Aggregates: counts and `trashed_bytes`. Dry-run returns the identical shape with nothing touched. The session accumulates trashed `(original_path, trash_path, bytes)` records to power surgical empty.

## Protected paths (core/safety.py)

Checked in order on the **resolved** path (symlink-safe), with path-component boundary matching (`/Systemwide` is not protected; `/System/x` is).

1. **System-critical (never touch):** `/System`, `/bin`, `/sbin`, `/usr` (except `/usr/local`), `/private/var/db`, `/Library/Apple`, boot volume roots.
2. **User-data (never touch):** `~/Documents`, `~/Desktop`, `~/Pictures`, any `*.photoslibrary`, `~/Library/Keychains`, `~/Library/Mail` (mailboxes, not caches), `~/.ssh`, `~/.gnupg`, iCloud Drive root, the Trash itself.
3. **In Use (conditional):** owner app currently running (decision 4). Skip reason names the app: "Skipped: Slack is running."

`is_protected(path)` returns `(True, "reason string")` so every skip is explainable.

## Safety registry (core/registry.py)

Every cleanable category declares:

| Field | Meaning |
|---|---|
| `key` | e.g. `browser_cache` |
| `level` | SAFE / CAUTION / RISKY — messaging only |
| `explanation` | One plain-English line: what it is, consequence of removal |
| `user_data` | True → individual explicit selection required (tripwire + UI rule) |
| `via_trash` | False → external tool / in-place mechanism; not recoverable via Trash |

Initial assignments:

| Category | level | user_data | via_trash |
|---|---|---|---|
| caches, logs, temp | SAFE | – | ✓ |
| browser_cache | SAFE | – | ✓ |
| xcode_derived_data, cocoapods_cache, pip_cache | SAFE | – | ✓ |
| brew_cleanup, npm_cache | SAFE | – | ✗ (external tool) |
| app_bundle | CAUTION | – | ✓ |
| app_leftovers, launch_agents | CAUTION | – | ✓ |
| tracking_data, browser_history | RISKY | – | ✓ |
| downloads, ios_backups | RISKY | ✓ | ✓ |
| large_files | RISKY | ✓ | ✓ |
| duplicates | RISKY | ✓ | ✓ |
| recents | RISKY | – | ✗ → **Irreversible Action** |
| snapshots | RISKY | – | ✗ → **Irreversible Action** |

`safe_delete` refuses any category not in the registry.

## Error handling

- `safe_delete` never raises for a single bad path; every path lands in the report.
- Trash failure (including ENOSPC) → `failed` with a human message suggesting reclaiming space. Never falls back to permanent delete.
- Unknown category, or `user_data` without `user_selected=True` → refuse the whole call (programming error).

## Testing (TDD, pytest)

- `tests/test_safety.py` — table-driven protected-path cases per tier; symlink-escape attempts; component-boundary cases; in-use protection with a mocked process list (running app → skipped with app name; quit app → passes; ownerless path → passes).
- `tests/test_deleter.py` — tmp-dir fixtures; trashing routes to the NSFileManager wrapper (mocked); skips carry reasons; report math adds up; unknown category refuses; user_data without tripwire flag raises; dry-run leaves files untouched; surgical-empty deletes exactly the recorded trash paths and nothing else.
- `tests/test_registry.py` — every category referenced by any cleaner exists; every entry has a non-empty explanation; Irreversible Action set is exactly {recents, snapshots}.
- Existing cleaner tests updated to assert delegation to `safe_delete`; `scan_all()` asserted to return no user_data categories.

## Out of scope (this phase)

- Textual UI (phase 2 consumes registry levels/explanations and the Space Finder model).
- New scanners — they inherit safety for free.
- Deletion-history manifest across sessions — the per-session trash records are the seed; persistence can be added without changing the `safe_delete` contract.
