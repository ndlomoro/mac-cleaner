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

- `1`-`6` navigate to an area (System Data/Junk, Space Finder, Privacy,
  Optimize, Snapshots, Uninstall Apps)
- `s` runs a Quick Scan across every area from the dashboard, without
  opening any of them
- `d` previews a dry run for the current area (nothing is touched)
- `c` cleans the current area for real (items move to the Trash)
- `v` toggles a per-file preview of what a category would touch, before
  you commit to a dry run or clean
- `t` moves picked items to the Trash (Space Finder - nothing is
  pre-selected; you choose each file)
- Uninstalling an app always runs a dry run first and shows you exactly
  what it found before asking for confirmation
- `escape` goes back, `q` quits

Tests: `python3 -m pytest tests/`
