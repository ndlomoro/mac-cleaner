# Trash-only deletion via NSFileManager, reported as Trashed — never "freed"

Status: accepted

Every file deletion goes through the macOS Trash using PyObjC's `NSFileManager.trashItemAtURL:resultingItemURL:error:`, and reports say bytes were **Trashed**, not freed — disk space is only called **Reclaimed** once it actually returns to the disk. This is the load-bearing decision behind the app's trust promise: undo always exists until the user explicitly gives it up.

## Considered Options

- **Direct delete (`rm`/`unlink`)** — reports honest "freed" numbers, but a single bad path is unrecoverable. Rejected: unacceptable for a tool whose core promise is safety.
- **`send2trash`** (the previous mechanism) — trashes files but does not return where they landed, and macOS renames on collision. That makes *surgical empty* (permanently deleting only what this app trashed, leaving the rest of the user's Trash intact) impossible without fragile name-guessing. Rejected for the NSFileManager API, which returns each item's resulting Trash URL. Costs a `pyobjc-framework-Cocoa` dependency — fine for a macOS-only app.
- **Whole-Trash empty after cleaning** — simpler, but destroys items the app never showed the user, breaking the "explain every deletion" promise. Rejected in favor of surgical empty over recorded `(original_path, trash_path)` pairs.

## Consequences

- "X GB freed!" can never appear after a mere clean; the UI must offer "Empty now to reclaim X" as a separate step.
- Deletions that structurally cannot use the Trash (tmutil snapshots, in-place clears, external tools like `brew cleanup`) are the registry-flagged exception (`via_trash=False`); the RISKY ones among them are Irreversible Actions requiring typed confirmation.
- A cleaner run on a 100%-full disk cannot fail into permanent deletion; it reports the failure and suggests reclaiming space.
