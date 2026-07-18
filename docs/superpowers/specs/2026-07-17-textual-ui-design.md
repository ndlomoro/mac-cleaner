# Textual UI — Design (Phase 2)

**Date:** 2026-07-17
**Status:** Approved
**Phase:** 2 of the rebuild program (safety core ✓ → **Textual UI** → dev-junk scanner → iOS backups/mail → smarter duplicates → orphaned app data)
**Vocabulary:** terms in bold are defined in `/CONTEXT.md`. User-facing strings remain bound by the Trashed/Reclaimed rules.

## Goal

Replace the Rich menu loop in `main.py` with a full-screen Textual app that makes the safety core's guarantees *visible*: level badges and explanations on every category, skips with reasons, honest Trashed-vs-Reclaimed wording, modal gates, and pick flows for **Reclaimable User Data** — including large files and duplicates, which close phase 1's two known debts.

## Scope decision (approved)

Full app + debts: the menu loop is deleted; scan-perf work lands first so the TUI never freezes; large files and duplicates join Space Finder's pick flow.

## Architecture

```
ui/
├── app.py            # CleanerApp(App): screen stack, keybindings, theme
├── screens/
│   ├── dashboard.py  # disk usage + category list (level badges) + last-scan summary
│   ├── junk.py       # System Data bulk flow (select-all allowed)
│   ├── space_finder.py # 4 tabs: Downloads, iOS Backups, Large Files, Duplicates
│   ├── privacy.py    # browser/tracking clean + gated recents
│   ├── optimize.py   # dev caches + brew/npm external-tool labels
│   ├── snapshots.py  # gated deletion, Reclaimed reporting
│   └── uninstall.py  # app picker + two-report view
├── widgets/
│   ├── category_header.py  # [LEVEL] badge + explanation (reads core.registry)
│   ├── report_view.py      # sole renderer for DeleteReport / ReclaimReport
│   └── gates.py            # ConfirmModal (y/N) + TypedGateModal (literal "yes") — the only gate implementations
```

(Streaming is per-screen: each screen runs its blocking scan in a Textual thread-worker and updates via `call_from_thread` — no separate workers module needed.)

**Contracts:**
- `main.py` becomes an entry point that launches `CleanerApp`. The menu loop is deleted (git history keeps it).
- The UI computes no safety decisions: levels, explanations, `user_data`, `irreversible` all come from `core.registry`. Screens mount the gate modal the registry demands.
- No scanner or cleaner runs on the UI thread. Workers post per-category partial results; screens populate progressively.

## Flows and selection semantics

- **Junk screen:** tree of caches/logs/temp, pre-selectable (SAFE junk). Dry Run / Clean → `report_view` → if trashed > 0, "Empty now to reclaim ~X?" mounts **TypedGateModal**.
- **Space Finder:** nothing pre-selected; the widget offers **no select-all** (structural enforcement of the user_data rule). Rows show size + age-as-signal. Check → footer total → Move to Trash → **ConfirmModal** (count + ~size) → `safe_delete(..., user_selected=True)` — genuinely true, paths come from checkbox state.
- **Duplicates:** new registry category `duplicates` (RISKY, user_data=True). Rows grouped by content hash; the UI enforces the **Keep-One Invariant** — at least one copy per group can never be selected.
- **Privacy/Optimize/Snapshots/Uninstall:** same widgets recombined; external-tool categories carry the passive "not recoverable via Trash" label; recents and snapshots mount TypedGateModal.
- **Gate rules:** ConfirmModal for trashing user_data selections; TypedGateModal for anything `irreversible` plus the reclaim/empty step. Dry runs never gate.

## Protection semantics amendment (approved during phase-2 design)

Phase 1's tier-2 protection made `~/Documents`, `~/Desktop`, `~/Pictures` absolutely undeletable — which would let Space Finder show, pick, and confirm a large file there and then refuse it. Tier 2 splits:

- **Soft-Protected** (`~/Documents`, `~/Desktop`, `~/Pictures`): immune to bulk/Junk cleaning exactly as before, but deletable through a `user_selected` pick flow (Trash-recoverable + confirmed).
- **Hard-Protected** (Keychains, Mail, `.ssh`, `.gnupg`, `*.photoslibrary`, iCloud Drive, the Trash, all system tiers): never deletable, picked or not.

`is_protected` gains an `allow_user_content` flag; `safe_delete` passes it only when the category is `user_data` AND `user_selected=True`.

## Perf debt (lands first)

- `scan_temp_files` collapses seven per-pattern `rglob` walks into one walk matching all patterns.
- `/private/var/folders` scanned shallowly (depth-capped, lazy sizing).
- Remaining latency surfaces as streaming progress, never a frozen screen.

## Hygiene bundle (from phase-1 final review)

In scope: `scan_all` junk-only test patches HOME; `resolve()` fail-safe test; app_remnants missing-bundle test; privacy real-run (fake-trash) test; delete the two `pass`-body baseline tests; tier reason strings name the matched root (now user-visible in report_view). Moot: `run_optimization` dead fallback dies with the menu loop.

## Testing

- Textual `run_test()` pilot tests drive real key presses: navigate → check → confirm → assert `safe_delete` received exactly the checked paths (reusing phase 1's fake-trash fixtures).
- Dedicated tests: Keep-One Invariant; TypedGateModal rejects everything but literal "yes"; Space Finder exposes no select-all binding; report_view renders skips with reasons.
- Packaging test: setup.py's py2app manifest must list every top-level package (prevents a repeat of phase 1's `core` omission).
- New deps: `textual` (pinned ≥1.0), `pytest-asyncio` for pilot tests.

## Out of scope

New scanners (phases 3–6), deletion-history persistence, settings screen, theming beyond Textual defaults + level colors.
