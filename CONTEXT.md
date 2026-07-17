# Mac Cleaner

A macOS disk cleaner that reclaims space safely. Its core promise: it never destroys anything a user would miss, and it can explain every deletion before it happens.

## Language

**Junk**:
Regenerable byproducts of normal computer use — caches, logs, temp files, dev build artifacts. Deleting junk costs nothing but a slower first reload. May be bulk-cleaned.
_Avoid_: system data, clutter

**Reclaimable User Data**:
Real user content the app surfaces because it consumes space — old downloads, iOS backups, large files, duplicates. Never junk, regardless of age. Each item must be individually and explicitly selected; never bulk-cleaned, never selected by default.
_Avoid_: old files, cleanable data

**Category**:
A named kind of cleanable item (e.g. caches, logs, ios_backups). Every category is registered with a safety level and a plain-English explanation before anything in it may be deleted.

**System Data**:
The junk-only scan area: caches, logs, temp files. Everything in it may be bulk-cleaned.
_Avoid_: system files, cleanup

**Space Finder**:
The browse-and-pick area for Reclaimable User Data: old downloads, iOS backups, large files, duplicates. Age is a signal shown to the user, never an eligibility filter.
_Avoid_: smart scan

**Keep-One Invariant**:
In any group of duplicate files, at least one copy can never be selected for removal. Enforced by the interface, not left to the user's care.

**Safety Level**:
How loudly the app warns about a category: SAFE, CAUTION, or RISKY. Describes the consequence of deletion; it does not by itself permit or forbid anything.
_Avoid_: severity, risk score

**Trashed**:
Sent to the macOS Trash: recoverable, and not yet free disk space. The app never reports Trashed bytes as freed.
_Avoid_: deleted, freed, cleaned

**Reclaimed**:
Space actually returned to the disk — after emptying trashed items or deleting a snapshot. The only number the app may call "freed".
_Avoid_: saved space

**In Use**:
A path whose owning app is currently running. In-use paths are skipped and the skip names the app ("Skipped: Slack is running"). Ownerless paths (e.g. /tmp) are never In Use.
_Avoid_: locked, busy

**Irreversible Action**:
A RISKY deletion that cannot go through the Trash and therefore cannot be undone (e.g. snapshot removal, recents-clear). Requires its own typed confirmation. Non-Trash deletion of mere Junk (e.g. brew cache) is not an Irreversible Action — it is labeled, not gated.
_Avoid_: permanent delete, hard delete
