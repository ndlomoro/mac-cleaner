"""The Keep-One Invariant, as a pure rule over Duplicate Groups.

A Duplicate Group (see CONTEXT.md) may never be emptied: at least one member
must survive any deletion. This module knows nothing about the filesystem, the
Trash, or the UI - it answers one question over plain path strings, so the
invariant can be proven synchronously instead of through a Textual screen.

The invariant is keeper-agnostic: it guarantees *a* survivor, not that the
labelled keeper is the one that stays.
"""
from collections.abc import Iterable


class KeepOneViolation(Exception):
    """A deletion would empty one or more Duplicate Groups. Carries the
    offending groups so callers can name them without re-deriving them."""

    def __init__(self, groups: list[frozenset[str]]):
        self.groups = groups
        super().__init__(
            f"deletion would remove every copy of {len(groups)} duplicate "
            f"group(s); one copy of each is always kept"
        )


def find_keep_one_violations(
    trashing: Iterable[str],
    groups: Iterable[frozenset[str]],
) -> list[frozenset[str]]:
    """Return the Duplicate Groups that `trashing` would empty, in input order.

    A group offends when it is non-empty and every one of its members is in
    `trashing` (checked over the union of all paths being trashed, so a group
    whose copies are reached from different tabs is still caught). An empty
    result means the deletion upholds the Keep-One Invariant.
    """
    trash_set = set(trashing)
    return [group for group in groups if group and group <= trash_set]
