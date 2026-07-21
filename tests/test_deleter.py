from pathlib import Path

import pytest

import core.deleter as deleter_mod
from core.dedup import KeepOneViolation
from core.deleter import (
    DeleteReport,
    Outcome,
    ReclaimReport,
    UserSelectionRequired,
    reclaim,
    safe_delete,
    trash_selection,
)
from core.registry import UnknownCategoryError


@pytest.fixture(autouse=True)
def no_live_process_lookup(monkeypatch):
    monkeypatch.setattr(deleter_mod, "running_apps", lambda: {})


@pytest.fixture
def fake_trash(monkeypatch, tmp_path):
    """Redirect trash_item to move files into a fake .Trash and return that path."""
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir()

    def _fake(path: Path) -> Path:
        dest = trash_dir / path.name
        path.rename(dest)
        return dest

    monkeypatch.setattr(deleter_mod, "trash_item", _fake)
    return trash_dir


def _items(*paths):
    return [{"path": str(p), "size": p.stat().st_size if p.exists() else 0} for p in paths]


def test_unknown_category_refuses(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(UnknownCategoryError):
        safe_delete(_items(f), "not_a_category")


def test_user_data_requires_tripwire(tmp_path):
    f = tmp_path / "backup"
    f.mkdir()
    with pytest.raises(UserSelectionRequired):
        safe_delete([{"path": str(f), "size": 10}], "ios_backups")
    # with the flag it proceeds (dry run so nothing is touched)
    report = safe_delete([{"path": str(f), "size": 10}], "ios_backups",
                         dry_run=True, user_selected=True)
    assert report.trashed_bytes == 10


def test_dry_run_touches_nothing(tmp_path):
    f = tmp_path / "cache.dat"
    f.write_bytes(b"12345")
    report = safe_delete(_items(f), "caches", dry_run=True)
    assert f.exists()
    assert report.dry_run
    assert len(report.trashed) == 1
    assert report.trashed_bytes == 5
    assert report.trashed[0].trash_path == ""


def test_real_delete_goes_to_trash(tmp_path, fake_trash):
    f = tmp_path / "cache.dat"
    f.write_bytes(b"12345")
    report = safe_delete(_items(f), "caches")
    assert not f.exists()
    assert (fake_trash / "cache.dat").exists()
    assert report.trashed[0].trash_path == str(fake_trash / "cache.dat")
    assert report.trashed_bytes == 5


def test_real_delete_remeasures_stale_file_size(tmp_path, fake_trash):
    """A regular file grown since the scan is accounted at its real size,
    not the scanner's cached estimate - so Reclaimed stays truthful."""
    f = tmp_path / "grew.bin"
    f.write_bytes(b"0" * 500)
    # Caller passes a stale scan-time size (100); the file is really 500.
    report = safe_delete([{"path": str(f), "size": 100}], "caches")
    assert report.trashed_bytes == 500
    assert report.trashed[0].size == 500


def test_dir_size_is_not_remeasured(tmp_path, fake_trash):
    """Directory sizes come from a scan-time tree walk; a live stat of the
    directory entry would undercount, so the cached size is kept."""
    d = tmp_path / "tree"
    d.mkdir()
    (d / "big.bin").write_bytes(b"0" * 4096)
    report = safe_delete([{"path": str(d), "size": 4096}], "caches")
    assert report.trashed_bytes == 4096


def test_protected_paths_skipped_with_reason(tmp_path, fake_trash):
    target = Path.home() / "Documents"
    link = tmp_path / "sneaky"
    link.symlink_to(target)
    report = safe_delete([{"path": str(link), "size": 1}], "caches")
    assert len(report.skipped) == 1
    assert report.skipped[0].reason
    assert len(report.trashed) == 0


def test_in_use_skip_names_the_app(tmp_path, monkeypatch, fake_trash):
    monkeypatch.setattr(deleter_mod, "running_apps",
                        lambda: {"com.example.app": "Example"})
    cache = Path.home() / "Library" / "Caches" / "com.example.app"
    report = safe_delete([{"path": str(cache), "size": 1}], "caches", dry_run=True)
    assert report.skipped[0].reason == "Example is running"


def test_vanished_file_is_skipped(tmp_path, fake_trash):
    report = safe_delete([{"path": str(tmp_path / "gone.txt"), "size": 3}], "caches")
    assert len(report.skipped) == 1
    assert "no longer exists" in report.skipped[0].reason


def test_failure_is_reported_not_raised(tmp_path, monkeypatch):
    def _boom(path):
        raise deleter_mod.TrashError("disk full")
    monkeypatch.setattr(deleter_mod, "trash_item", _boom)
    f = tmp_path / "cache.dat"
    f.write_bytes(b"123")
    report = safe_delete(_items(f), "caches")
    assert len(report.failed) == 1
    assert "disk full" in report.failed[0].reason
    assert f.exists()  # never permanently deleted on failure


def test_report_math_adds_up(tmp_path, fake_trash):
    a = tmp_path / "a.txt"; a.write_bytes(b"11")
    b = tmp_path / "b.txt"; b.write_bytes(b"222")
    gone = tmp_path / "gone.txt"
    items = _items(a, b) + [{"path": str(gone), "size": 9}]
    report = safe_delete(items, "caches")
    assert len(report.results) == 3
    assert len(report.trashed) == 2
    assert len(report.skipped) == 1
    assert report.trashed_bytes == 5


def test_malformed_item_fails_without_killing_report(tmp_path, fake_trash):
    good = tmp_path / "good.txt"; good.write_bytes(b"1234")
    items = [{"size": 5}, {"path": str(good), "size": 4}]  # first item has no "path"
    report = safe_delete(items, "caches")
    assert len(report.results) == 2
    assert len(report.failed) == 1
    assert "malformed" in report.failed[0].reason
    assert len(report.trashed) == 1
    assert (fake_trash / "good.txt").exists()


def test_unexpected_exception_reported_not_raised(tmp_path, monkeypatch):
    def _boom(path):
        raise RuntimeError("pyobjc bridge exploded")
    monkeypatch.setattr(deleter_mod, "trash_item", _boom)
    f = tmp_path / "cache.dat"; f.write_bytes(b"123")
    report = safe_delete(_items(f), "caches")
    assert len(report.failed) == 1
    assert "exploded" in report.failed[0].reason
    assert f.exists()


def test_wrong_typed_path_fails_without_killing_report(tmp_path, fake_trash):
    good = tmp_path / "good.txt"; good.write_bytes(b"12")
    items = [{"path": 123, "size": 1}, {"path": None, "size": 1},
             {"path": str(good), "size": 2}]
    report = safe_delete(items, "caches")
    assert len(report.results) == 3
    assert len(report.failed) == 2
    assert all("malformed" in r.reason for r in report.failed)
    assert len(report.trashed) == 1


def test_reclaim_deletes_only_our_items(tmp_path, fake_trash):
    ours = tmp_path / "ours.txt"; ours.write_bytes(b"1234")
    theirs = fake_trash / "users-own-trashed-file.txt"
    theirs.write_text("user put this in the Trash last week")

    report = safe_delete(_items(ours), "caches")
    result = reclaim([report])

    assert isinstance(result, ReclaimReport)
    assert result.deleted == 1
    assert result.freed_bytes == 4
    assert not (fake_trash / "ours.txt").exists()
    assert theirs.exists()  # the rest of the Trash is untouched


def test_reclaim_ignores_dry_run_reports(tmp_path):
    f = tmp_path / "f.txt"; f.write_bytes(b"12")
    report = safe_delete(_items(f), "caches", dry_run=True)
    result = reclaim([report])
    assert result.deleted == 0
    assert f.exists()


def test_reclaim_counts_failures(tmp_path, fake_trash):
    f = tmp_path / "f.txt"; f.write_bytes(b"12")
    report = safe_delete(_items(f), "caches")
    (fake_trash / "f.txt").unlink()  # someone emptied the Trash already
    result = reclaim([report])
    assert result.deleted == 0
    # already-gone items are not failures; nothing to delete
    assert result.failed == 0


def test_reclaim_reports_delete_failures(tmp_path, fake_trash, monkeypatch):
    f = tmp_path / "f.txt"; f.write_bytes(b"12")
    report = safe_delete(_items(f), "caches")
    def _denied(path):
        raise OSError("permission denied")
    monkeypatch.setattr(deleter_mod, "delete_from_trash", _denied)
    result = reclaim([report])
    assert result.deleted == 0
    assert result.failed == 1
    assert result.freed_bytes == 0


def test_user_selected_unlocks_soft_protected(tmp_path, monkeypatch, fake_trash):
    # a downloads-category item living under a Soft-Protected dir, dry-run
    doc = Path.home() / "Documents" / "never-created.bin"
    report = safe_delete([{"path": str(doc), "size": 5}], "downloads",
                         dry_run=True, user_selected=True)
    # soft protection yielded: not skipped-as-protected (it's TRASHED in dry-run;
    # nonexistence is only checked on real runs)
    assert len(report.trashed) == 1


def test_junk_categories_never_unlock_soft_protection(tmp_path, fake_trash):
    doc = Path.home() / "Documents" / "never-created.bin"
    report = safe_delete([{"path": str(doc), "size": 5}], "caches", dry_run=True)
    assert len(report.skipped) == 1


# ---------- trash_selection: the Keep-One Invariant behind the interface ----------


def test_trash_selection_dispatches_each_category(tmp_path, fake_trash):
    a = tmp_path / "a.bin"; a.write_bytes(b"1234")
    b = tmp_path / "b.bin"; b.write_bytes(b"55")
    submission = {
        "large_files": _items(a),
        "downloads": _items(b),
    }
    reports = trash_selection(submission, groups=[])
    assert [r.category for r in reports] == ["large_files", "downloads"]
    assert not a.exists() and not b.exists()
    assert (fake_trash / "a.bin").exists()
    assert (fake_trash / "b.bin").exists()


def test_trash_selection_upholds_keep_one_and_touches_nothing(tmp_path, fake_trash):
    x = tmp_path / "x.bin"; x.write_bytes(b"1234")
    y = tmp_path / "y.bin"; y.write_bytes(b"1234")
    group = frozenset({str(x), str(y)})
    submission = {"duplicates": _items(x, y)}
    with pytest.raises(KeepOneViolation) as err:
        trash_selection(submission, groups=[group])
    assert err.value.groups == [group]
    # fail-closed: the whole batch is refused, both copies survive on disk
    assert x.exists() and y.exists()
    assert not (fake_trash / "x.bin").exists()
    assert not (fake_trash / "y.bin").exists()


def test_trash_selection_allows_partial_group(tmp_path, fake_trash):
    x = tmp_path / "x.bin"; x.write_bytes(b"1234")
    y = tmp_path / "y.bin"; y.write_bytes(b"1234")
    group = frozenset({str(x), str(y)})
    # only one copy of the group is selected -> a survivor remains -> allowed
    submission = {"duplicates": _items(x)}
    reports = trash_selection(submission, groups=[group])
    assert not x.exists()
    assert y.exists()
    assert reports[0].trashed[0].path == str(x)


def test_trash_selection_checks_the_cross_category_union(tmp_path, fake_trash):
    # a group's two copies are picked from DIFFERENT tabs; neither category on
    # its own empties the group, but the union does -> must be caught.
    x = tmp_path / "x.bin"; x.write_bytes(b"1234")
    y = tmp_path / "y.bin"; y.write_bytes(b"1234")
    group = frozenset({str(x), str(y)})
    submission = {
        "duplicates": _items(x),
        "large_files": _items(y),
    }
    with pytest.raises(KeepOneViolation):
        trash_selection(submission, groups=[group])
    assert x.exists() and y.exists()


def test_trash_selection_dry_run_validates_but_touches_nothing(tmp_path, fake_trash):
    x = tmp_path / "x.bin"; x.write_bytes(b"1234")
    y = tmp_path / "y.bin"; y.write_bytes(b"1234")
    group = frozenset({str(x), str(y)})
    # even a dry run refuses a batch that would empty a group
    with pytest.raises(KeepOneViolation):
        trash_selection({"duplicates": _items(x, y)}, groups=[group], dry_run=True)
    # a valid dry run reports without trashing
    reports = trash_selection({"duplicates": _items(x)}, groups=[group], dry_run=True)
    assert reports[0].dry_run
    assert x.exists()


def test_trash_selection_passes_user_selected_tripwire(tmp_path, fake_trash):
    # downloads is a user_data category; trash_selection must supply the
    # user_selected tripwire or safe_delete would raise UserSelectionRequired.
    doc = Path.home() / "Documents" / "never-created-selection.bin"
    reports = trash_selection(
        {"downloads": [{"path": str(doc), "size": 5}]},
        groups=[], dry_run=True,
    )
    assert len(reports[0].trashed) == 1  # soft-protection unlocked, no raise
