# Dev-Junk Scanner — Design (Phase 3)

**Date:** 2026-07-18
**Status:** Approved
**Phase:** 3 of the rebuild (safety core ✓ → Textual UI ✓ → **dev-junk scanner** → iOS backups/mail → smarter duplicates → orphaned app data)
**Vocabulary:** `/CONTEXT.md` binding (Trashed ≠ Reclaimed, Hard/Soft-Protected, Keep-One, and the new **Stale** term).

## Goal

Surface and reclaim developer artifacts — the biggest space hogs on dev machines — without ever surprising an active project: per-project pick flows sorted by staleness, and gated external-tool cleanup for Docker and iOS Simulators.

## Scope decision (approved)

Staleness-aware pick screen (Space Finder style) for filesystem artifacts; Docker and Simulators as separate TypedGate-gated external sections; ride-alongs: screen-resume rescans and routing Space Finder's large-files tab through `clean_large_files`. De-scoped: Docker image cherry-picking, per-language cache tuning, `_busy` naming unification, duplicates perf.

## Scanner (`scanner/dev_junk.py`)

- `find_project_artifacts() -> list[dict]` — `{path, size, age_days, kind, project}`.
  Kinds: `node_modules` (sibling `package.json`), `venv` (`pyvenv.cfg` inside), `rust_target` (sibling `Cargo.toml`), `gradle_cache` (`~/.gradle/caches`), `maven_repo` (`~/.m2/repository`).
  Roots: `~/Documents`, `~/Develop*`, `~/Projects`, `~` (depth-capped) — module-level list, monkeypatchable.
  **Staleness:** `age_days` = days since the *project's* newest source-file mtime (excluding the artifact itself) — an `npm install` yesterday in a dead project does not make it active. Signal, never a filter.
  Cost control: prune at first artifact hit (never descend into `node_modules`/`target`/venv); `get_dir_size` per artifact only.
- `find_docker_junk() -> dict | None` — `docker system df` JSON: images/volumes/build-cache sizes; `None` when no docker CLI.
- `find_simulators() -> list[dict]` — `xcrun simctl list -j`: unavailable runtimes/devices + sizes; `[]` when no Xcode.

## Registry additions

| key | level | user_data | via_trash |
|---|---|---|---|
| `project_artifacts` | CAUTION | ✓ | ✓ |
| `docker_junk` | RISKY | – | ✗ (external: docker prune) |
| `ios_simulators` | RISKY | – | ✗ (external: simctl delete unavailable) |

`project_artifacts` is user_data=True deliberately: regenerable but disruptive — the no-bulk-clean tripwire applies. Docker/sims derive `irreversible=True` from the registry (RISKY + non-Trash) — gates come from the existing derivation, no new gate logic.

## Dev Junk screen (`ui/screens/dev_junk.py`, dashboard key 7)

1. **Project artifacts:** SelectionList, stalest-first (`"{~size}  {age}d idle  {kind}  {project}"`), nothing pre-selected, no select-all, selected-total footer. Pick → ConfirmModal → `safe_delete(..., user_selected=True)` off-thread → ReportView → reclaim offer. Inherits: run_offthread, busy guard, skipped-items-stay-listed refresh.
2. **Docker** (present only when CLI exists): summary line; `D` → TypedGateModal naming exactly what the prune covers; **volumes excluded by default**, included only via a separate explicit prompt (they can hold real data). Reports Docker's own figure as genuinely Reclaimed.
3. **Simulators** (present only when Xcode exists): list of unavailable simulators by name (sizing ticketed for a later polish pass along with the None-vs-[] absent-tool distinction); `S` → TypedGateModal → `xcrun simctl delete unavailable` (conservative variant only).

**Quick Scan:** dashboard gains a "Dev junk: ~X across N projects" line — project discovery only; no docker/simctl subprocess calls from the dashboard.

## Ride-alongs

- **Screen-resume rescans:** an `on_screen_resume` refresh in the shared flow — all screens re-scan when revisited (fixes stale counts after cleaning).
- **clean_large_files routing:** Space Finder's large-files tab delegates to `cleaner.large_files.clean_large_files` — the tripwire-stamping helper gains its one honest caller.

## Testing

Scanner: tmp project trees with controlled mtimes (kind detection, staleness vs artifact-touch, prune-at-first-hit, depth cap); docker/simctl parsers against canned JSON via monkeypatched run_command — tests never invoke real docker/xcrun; absent-tool paths covered. Screens: inherited pilot patterns; `D`/`S` assert the external command does NOT run without literal "yes"; volumes prompt defaults excluded. Resume: revisit → scanner called again. Registry: irreversible set becomes {recents, snapshots, docker_junk, ios_simulators}.

## Out of scope

Xcode DerivedData/archives (Optimize owns them), `~/.npm`/pip caches (covered), Docker image-level selection, phases 4–6.
