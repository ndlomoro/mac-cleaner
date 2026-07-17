from pathlib import Path

import pytest

import core.deleter as deleter_mod
from core.deleter import DeleteReport, Outcome, UserSelectionRequired, safe_delete
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
