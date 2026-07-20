"""The Keep-One Invariant as a pure function - no I/O, no Textual pilot.

A Duplicate Group may never be emptied: at least one member always survives.
Keeper-agnostic (see CONTEXT.md) - it guarantees a survivor, not which one.
"""
from core.dedup import KeepOneViolation, find_keep_one_violations


def _groups(*members):
    return [frozenset(m) for m in members]


def test_no_groups_never_violates():
    assert find_keep_one_violations({"/a", "/b"}, []) == []


def test_partial_selection_is_allowed():
    # one member trashed, one survives -> fine
    groups = _groups(["/g1/a", "/g1/b"])
    assert find_keep_one_violations({"/g1/a"}, groups) == []


def test_full_selection_of_a_group_is_a_violation():
    groups = _groups(["/g1/a", "/g1/b"])
    violations = find_keep_one_violations({"/g1/a", "/g1/b"}, groups)
    assert violations == [frozenset({"/g1/a", "/g1/b"})]


def test_selecting_all_but_one_is_the_boundary():
    groups = _groups(["/g/a", "/g/b", "/g/c"])
    # two of three trashed -> the third survives -> allowed
    assert find_keep_one_violations({"/g/a", "/g/b"}, groups) == []
    # all three -> violation
    assert find_keep_one_violations({"/g/a", "/g/b", "/g/c"}, groups) == [
        frozenset({"/g/a", "/g/b", "/g/c"})
    ]


def test_cross_category_union_is_what_counts():
    # a group's members can be reached from different tabs; the invariant is
    # checked over the UNION of everything being trashed, not per-category.
    groups = _groups(["/dup/x", "/dup/y"])
    trashing = {"/dup/x", "/dup/y"}  # x from Duplicates tab, y from Large Files
    assert find_keep_one_violations(trashing, groups) == [
        frozenset({"/dup/x", "/dup/y"})
    ]


def test_only_offending_groups_are_returned():
    groups = _groups(
        ["/g1/a", "/g1/b"],   # fully covered -> offends
        ["/g2/a", "/g2/b"],   # partially covered -> fine
        ["/g3/a", "/g3/b"],   # fully covered -> offends
    )
    trashing = {"/g1/a", "/g1/b", "/g2/a", "/g3/a", "/g3/b"}
    violations = find_keep_one_violations(trashing, groups)
    assert violations == [
        frozenset({"/g1/a", "/g1/b"}),
        frozenset({"/g3/a", "/g3/b"}),
    ]


def test_empty_group_is_not_a_violation():
    # a vacuous group has nothing to empty
    assert find_keep_one_violations({"/a"}, [frozenset()]) == []


def test_extra_trashed_paths_outside_any_group_are_ignored():
    groups = _groups(["/g/a", "/g/b"])
    # trashing includes unrelated files; the group itself keeps a survivor
    assert find_keep_one_violations({"/g/a", "/other", "/misc"}, groups) == []


def test_accepts_any_iterable_of_trashed_paths():
    groups = _groups(["/g/a", "/g/b"])
    assert find_keep_one_violations(["/g/a", "/g/b"], groups) == [
        frozenset({"/g/a", "/g/b"})
    ]


def test_keep_one_violation_carries_the_groups():
    groups = [frozenset({"/g/a", "/g/b"})]
    err = KeepOneViolation(groups)
    assert err.groups == groups
    assert "duplicate" in str(err).lower()
