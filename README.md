# mac-cleaner

A macOS system cleaner built around one promise: it never destroys anything
you'd miss. Everything goes through the Trash (recoverable until *you* empty
it), every category explains itself, and irreversible actions require typed
confirmation. See CONTEXT.md for the vocabulary and docs/adr/ for key decisions.

Documents, Desktop and Pictures are immune to bulk cleaning; individually
picked files there can be Trashed after an explicit confirm. Keychains, SSH
keys, Photos libraries and iCloud Drive can never be touched. Mail is more
nuanced - see "Mail Junk" below: **mailbox content is never touched - only
attachment copies and caches** are ever cleanable.

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

## Mail Junk (part of System Data, key 1)

Two SAFE categories, scanned alongside caches/logs/temp/browser-cache:

- **Mail Attachment Copies** - cached copies of attachments you've already
  opened in Mail (both the modern `~/Library/Containers/com.apple.mail/...`
  location and the legacy `~/Library/Mail Downloads` sibling folder).
- **Mail Caches** - Mail's own rebuildable cache files.

The hard boundary: **mailbox content is never touched - only attachment
copies and caches are**. `~/Library/Mail` itself (the actual mailbox store)
is structurally off-limits - the scanner is written so it cannot emit a path
from inside it, even from the legacy-location list, no matter what's on
disk. Mail recreates anything removed here on its own; nothing you've
written or received is at risk.

## Space Finder (key 2)

Four tabs, each RISKY - real user content, nothing pre-selected, you pick
items individually and Trash them with `t`:

- **Downloads** - files in `~/Downloads`.
- **iOS Backups** - device backups under `~/Library/Application
  Support/MobileSync/Backup`. Each row that carries readable metadata shows
  the device name, iOS version and staleness at a glance, e.g.
  `1.23 MB   42d since backup  Nick's iPhone (iOS 17.4)` - so the backup
  you haven't refreshed in the longest time is easy to spot. Rows whose
  `Info.plist` can't be read (missing/corrupt) fall back to the generic
  size/age/path label instead of guessing. The scanner only ever reads
  `Info.plist` for this metadata - it never opens `Manifest.plist` /
  `Manifest.db` (the encrypted-backup internals), so backup integrity is
  never at risk.
- **Large Files** - individually large files anywhere on disk.
- **Duplicates** - extra copies of identical files; one copy of each set is
  always kept automatically, you choose which of the rest go.

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
