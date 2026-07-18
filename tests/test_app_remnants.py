import pytest
from pathlib import Path
import scanner.app_remnants
import cleaner.app_remnants
import core.deleter as deleter_mod
from core.deleter import DeleteReport
from scanner.app_remnants import find_leftovers, get_installed_apps
from cleaner.app_remnants import clean_leftovers, uninstall_app

def test_find_leftovers(tmp_path, monkeypatch):
    # Setup mock leftover directories
    app_support = tmp_path / "Application Support"
    app_support.mkdir()

    pref_dir = tmp_path / "Preferences"
    pref_dir.mkdir()

    # Leftover files
    sup_file = app_support / "TestApp_data"
    sup_file.write_bytes(b"support data")

    pref_file = pref_dir / "com.test.TestApp.plist"
    pref_file.write_bytes(b"pref data")

    # Mock LIBRARY to point to our tmp_path
    monkeypatch.setattr(scanner.app_remnants, "LIBRARY", tmp_path)
    # Mock LEFTOVER_PATHS to match our mock paths
    mock_leftover_paths = [
        (app_support, "{app}*", "{app}"),
        (pref_dir, "com.*{app}*", "*{app}*"),
    ]
    monkeypatch.setattr(scanner.app_remnants, "LEFTOVER_PATHS", mock_leftover_paths)

    leftovers = find_leftovers("TestApp")

    # Verify leftovers found
    assert len(leftovers) == 2
    paths = [l["path"] for l in leftovers]
    assert str(sup_file) in paths
    assert str(pref_file) in paths


def _fake_trash(monkeypatch, tmp_path):
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir(exist_ok=True)

    def _fake(path):
        dest = trash_dir / path.name
        path.rename(dest)
        return dest

    monkeypatch.setattr(deleter_mod, "trash_item", _fake)
    monkeypatch.setattr(deleter_mod, "running_apps", lambda: {})
    return trash_dir


def test_clean_leftovers_reports(tmp_path, monkeypatch):
    _fake_trash(monkeypatch, tmp_path)
    leftover = tmp_path / "com.testapp.plist"
    leftover.write_text("x")
    monkeypatch.setattr("cleaner.app_remnants.find_leftovers",
                        lambda name: [{"path": str(leftover), "size": 1, "type": "file"}])
    report = clean_leftovers("TestApp", dry_run=False)
    assert isinstance(report, DeleteReport)
    assert report.category == "app_leftovers"
    assert not leftover.exists()


def test_uninstall_app_returns_two_reports(tmp_path, monkeypatch):
    trash_dir = _fake_trash(monkeypatch, tmp_path)
    apps_dir = tmp_path / "Applications"
    apps_dir.mkdir()
    bundle = apps_dir / "TestApp.app"
    bundle.mkdir()
    monkeypatch.setattr("cleaner.app_remnants.APPLICATIONS_DIR", apps_dir)
    monkeypatch.setattr("cleaner.app_remnants.find_leftovers", lambda name: [])

    result = uninstall_app("TestApp", dry_run=False)
    assert isinstance(result["app"], DeleteReport)
    assert result["app"].category == "app_bundle"
    assert len(result["app"].trashed) == 1
    assert not bundle.exists()
    assert (trash_dir / "TestApp.app").exists()
    assert isinstance(result["leftovers"], DeleteReport)


def test_uninstall_app_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr("cleaner.app_remnants.APPLICATIONS_DIR", tmp_path)
    with pytest.raises(ValueError):
        uninstall_app("../../private/etc/foo")
    with pytest.raises(ValueError):
        uninstall_app("")


def test_clean_leftovers_rejects_path_traversal():
    with pytest.raises(ValueError):
        clean_leftovers("..")


def test_uninstall_missing_bundle_returns_empty_report(tmp_path, monkeypatch, no_running_apps):
    monkeypatch.setattr("cleaner.app_remnants.APPLICATIONS_DIR", tmp_path)
    monkeypatch.setattr("cleaner.app_remnants.find_leftovers", lambda name: [])
    result = uninstall_app("GhostApp", dry_run=False)
    assert result["app"].results == []
    assert result["app"].category == "app_bundle"
