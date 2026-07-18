# mac-cleaner

A macOS system cleaner built around one promise: it never destroys anything
you'd miss. Everything goes through the Trash (recoverable until *you* empty
it), every category explains itself, and irreversible actions require typed
confirmation. See CONTEXT.md for the vocabulary and docs/adr/ for key decisions.

Documents, Desktop and Pictures are immune to bulk cleaning; individually
picked files there can be Trashed after an explicit confirm. Keychains, Mail,
SSH keys, Photos libraries and iCloud Drive can never be touched.

## Usage

```
python3 main.py
```

This launches a full-screen terminal UI. From the dashboard:

- `1`-`7` navigate to an area (System Data/Junk, Space Finder, Privacy,
  Optimize, Snapshots, Uninstall Apps, Dev Junk)
- `s` runs a Quick Scan across every area from the dashboard, without
  opening any of them - it now includes a Dev Junk line (total size across
  affected projects) alongside the other categories
- `d` previews a dry run for the current area (nothing is touched)
- `c` cleans the current area for real (items move to the Trash)
- `v` toggles a per-file preview of what a category would touch, before
  you commit to a dry run or clean
- `t` moves picked items to the Trash (Space Finder, Dev Junk - nothing
  is pre-selected; you choose each item)
- Uninstalling an app always runs a dry run first and shows you exactly
  what it found before asking for confirmation
- `escape` goes back, `q` quits

## Dev Junk (key 7)

Build artifacts, dependency folders and caches (`node_modules`, Rust
`target`, Python venvs, Gradle/Maven caches) from projects under
`~/Documents`, `~/Develop`, `~/Developer` and `~/Projects`. Nothing is
pre-selected; you pick items individually, same as Space Finder. Each row
shows an idle-days figure measured from the *project's own source files*
(never the artifact itself), and the list is sorted stalest-first so the
project you haven't touched in the longest time surfaces at the top.
Picked items are moved to the Trash exactly like every other user-data
category - recoverable until you empty it.

Docker and iOS Simulators are a different shape: they're cleared by their
own tools (`docker`, `xcrun`), not routed through the Trash, so those
actions are genuinely irreversible and gated behind a typed confirmation:

- **Docker Prune** (`D`) runs `docker system prune -af` (images + build
  cache). Pruning volumes is a *separate, strictly opt-in* confirmation
  step - volumes can hold real data (databases, etc.) and are never
  included by default.
- **Clean Simulators** (`S`) deletes unavailable Xcode simulator devices
  via `xcrun simctl delete unavailable`.

Both sections stay hidden if the corresponding tool (`docker`/`xcrun`)
isn't installed.

Tests: `python3 -m pytest tests/`

**Known gap:** automated tests cover the scanners, deletion logic and
screen wiring, but there is no automated end-to-end smoke test of the
live terminal UI. A human `python3 main.py` walkthrough remains the
standing manual check before merging UI-facing changes.
