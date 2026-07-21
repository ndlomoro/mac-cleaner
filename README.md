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
python3 main.py           # the interactive menu (default)
python3 main.py --tui     # the full-screen Textual UI (kept alongside)
```

The default is a Rich text menu: a live disk header over a numbered list.
Pick a number to work an area; each area scans, shows what it found, gates,
acts, and returns you to the menu.

- `1` **Quick Scan** - read-only report across the junk categories; nothing
  is touched
- `2` **System Junk** - caches, logs, temp, mail copies (all SAFE); previews
  what would be Trashed, confirms, then moves it to the Trash
- `3` **Space Finder** - Downloads, iOS backups, large files, duplicates;
  nothing is pre-selected, you pick each row, and the Keep-One Invariant is
  enforced behind the deletion interface (a duplicate group can never be
  fully emptied)
- `4` **Privacy** - Trash browser/tracking caches, or clear the recent-items
  list (an Irreversible Action, typed-gate); browser history is shown but
  never deleted
- `5` **Optimize** - developer caches (Xcode/CocoaPods/pip go to the Trash;
  brew/npm clean via their own tools)
- `6` **Snapshots** - delete local Time Machine snapshots (Irreversible,
  typed-gate)
- `7` **Uninstall App** - Trash an app bundle and its leftovers, dry run
  shown first
- `8` **Dev Junk** - project artifacts to the Trash; Docker prune and
  simulator cleanup run via their own tools (Irreversible, typed-gate,
  volumes opt-in)

Recoverable actions ask for a `y/N` confirm; Irreversible Actions require you
to type `yes`. After anything is Trashed you're offered a typed-gate reclaim
to permanently empty exactly what was just trashed.

## Mail Junk (part of System Junk, key 2)

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

## Space Finder (key 3)

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
- **Duplicates** - extra copies of identical files, found via a three-stage
  scan (group by size, then by a cheap first-64KB partial hash, then a
  full-content hash - so the expensive full hash only ever runs on files
  that already agree on size and on their first 64KB) so large trees scan
  fast. Only files at least 1MB are considered; nothing smaller is worth
  the hashing cost. Within each group the app suggests a **Keeper** - the
  copy it'd keep, marked `★ keep` in the row - chosen by preferring a
  canonical location (Pictures/Documents/Movies/Music over scratch space
  like Downloads/Desktop), then a shallower path, then the older copy.
  The Keeper is never auto-selected for removal; press `k` to select every
  non-keeper row across all groups in one keystroke, or pick rows
  individually - either way, nothing is ever pre-selected and the Keep-One
  Invariant means at least one copy per group can never go.

## Dev Junk (key 8)

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

**Known gap:** automated tests cover the scanners, deletion logic, the CLI
flows (via a scripted stand-in UI) and the Textual screen wiring, but there
is no automated end-to-end smoke test driving a real terminal. A human
`python3 main.py` walkthrough (and `--tui` for the Textual UI) remains the
standing manual check before merging UI-facing changes.
