# iOS Backups & Mail — Design (Phase 4)

**Date:** 2026-07-18
**Status:** Approved
**Phase:** 4 of the rebuild (safety core ✓ → Textual UI ✓ → dev-junk ✓ → **iOS backups & mail** → smarter duplicates → orphaned app data)
**Vocabulary:** `/CONTEXT.md` binding.

## Goal

Make iOS backup rows informative enough to decide on ("Nick's iPhone 11 — 941d since backup — 38 GB", not a UDID hash), and reclaim the Mail junk the safety core permits — without ever parsing or touching mailbox content.

## Scope decision (approved)

Rich backups + safe Mail. The read-only mailbox attachment analyzer is deferred. `~/Library/Mail` stays Hard-Protected and untouchable.

## Scanners

- **`scanner/ios_backups.py`** — replaces `scan_ios_backups`'s internals (same ScanResult contract, category `ios_backups` unchanged: RISKY, user_data). Per backup dir under `MobileSync/Backup`: read `Info.plist` READ-ONLY via `plistlib` → row fields gain `device_name`, `ios_version`; `age_days` = days since `Last Backup Date` (real staleness). Unparseable/missing plist (incl. encrypted-manifest backups — we never read Manifest) → graceful fallback: dir-name row, mtime age, still listed. Never an exception, never a dropped row.
- **`scanner/mail_junk.py`** — two functions returning ScanResults, joined into `scan_all()` (they are Junk):
  - `mail_downloads`: `~/Library/Containers/com.apple.mail/Data/Library/Mail Downloads` + legacy `~/Library/Mail Downloads` (a SIBLING of ~/Library/Mail, not a child).
  - `mail_cache`: `~/Library/Caches/com.apple.mail` + the container's `Caches`.
  - Structural guard (pinned by test): the mail scanner can never emit a path under `~/Library/Mail`.

## Registry additions

| key | level | user_data | via_trash |
|---|---|---|---|
| `mail_downloads` | SAFE | – | ✓ |
| `mail_cache` | SAFE | – | ✓ |

Explanations: mail_downloads — "Copies of attachments you've opened in Mail. The originals stay in your mailboxes."; mail_cache — "Mail's rebuildable caches; Mail recreates them on next launch."

## UI

- Space Finder iOS tab renders enriched rows: `"{~size}  {age}d since backup  {device_name} (iOS {ios_version})"`, falling back to the dir-name form when metadata is absent. Only UI change of the phase.
- Mail categories ride the existing Junk screen / Quick Scan / bulk clean via `scan_all()` — zero new UI.

## Testing

Plist fixtures in tmp trees (well-formed, missing keys, corrupt file, future date); the never-under-`~/Library/Mail` guard; `scan_all` junk-only allowed-set extended with the two mail categories (bait-file guard retained); pilot test for enriched labels + fallback row. Tests never read the real MobileSync/Mail dirs.

## Out of scope

Mailbox attachment analyzer (deferred), encrypted-backup internals (outer Info.plist only), Messages/Photos, the phase-3 ticket backlog (carries forward).
