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

**Hard-Protected**:
Paths the app can never delete under any circumstances: keychains, mail stores, SSH/GPG keys, Photos libraries, iCloud Drive, the Trash itself, and all system paths.
_Avoid_: blacklisted, forbidden

**Soft-Protected**:
User-content folders (Documents, Desktop, Pictures) that bulk cleaning can never touch, but an individually picked and confirmed selection can send to the Trash.
_Avoid_: semi-protected

**Duplicate Group**:
A set of files with identical content, discovered by the duplicates scan. Membership is the whole set — every copy, including the ones the user leaves alone. One member is labelled the Keeper, but the label carries no safety weight.
_Avoid_: duplicate set, dupe cluster

**Keep-One Invariant**:
No Duplicate Group may be emptied: at least one member always survives a deletion. Keeper-agnostic — the invariant guarantees a survivor, not that the labelled Keeper is the one that stays. Enforced behind the deletion interface (`core.dedup` + `core.deleter.trash_selection`) over full group membership, so it holds no matter which caller reaches deletion — never left to a UI guard. The UI's live selection feedback is convenience, not the backstop.
_Avoid_: keep-a-copy, at-least-one rule

**Keeper**:
The copy of a Duplicate Group the app suggests keeping — marked ★, never auto-selected for removal. Advisory only: it drives the badge and the one-keystroke non-keeper selection, but the Keep-One Invariant protects a survivor regardless of which copy holds the label.
_Avoid_: original, master

**Safety Level**:
How loudly the app warns about a category: SAFE, CAUTION, or RISKY. Describes the consequence of deletion; it does not by itself permit or forbid anything.
_Avoid_: severity, risk score

**Stale**:
A project whose newest source-file change is long past. Staleness is measured on the project, never on its build artifacts (reinstalling dependencies does not make a dead project active). A signal shown to the user, never an eligibility filter.
_Avoid_: old, unused

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
