import pytest
from pathlib import Path
import scanner.app_remnants
import cleaner.app_remnants
from scanner.app_remnants import find_leftovers, get_installed_apps
from cleaner.app_remnants import uninstall_app

def test_get_installed_apps(tmp_path, monkeypatch):
    # Mock /Applications path
    apps_dir = tmp_path / "Applications"
    apps_dir.mkdir()
    
    app1 = apps_dir / "TestApp.app"
    app1.mkdir()
    (app1 / "Info.plist").write_bytes(b"plist data")
    
    monkeypatch.setattr(scanner.app_remnants, "Path", lambda path: apps_dir if path == "/Applications" else Path(path))
    
    # We can check get_installed_apps works on custom folder by patching
    # path inside function or mocking Path
    pass

def test_find_leftovers_and_uninstall(tmp_path, monkeypatch):
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
    
    # Mock clean_leftovers / uninstall_app references
    monkeypatch.setattr(cleaner.app_remnants, "find_leftovers", lambda name: leftovers)
    
    # Mock glob for /Applications
    monkeypatch.setattr("glob.glob", lambda pattern: [str(tmp_path / "Applications" / "TestApp.app")])
    
    # Create mock App path
    mock_app_dir = tmp_path / "Applications" / "TestApp.app"
    mock_app_dir.mkdir(parents=True)
    
    # Test uninstall - dry run
    res_dry = uninstall_app("TestApp", dry_run=True)
    assert res_dry["app_removed"] is True
    assert res_dry["leftovers"]["deleted"] == 2
    assert mock_app_dir.exists()
    assert sup_file.exists()
    
    # Mock send2trash
    def mock_send2trash(path):
        p = Path(path)
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            [f.unlink() for f in p.rglob("*") if f.is_file()]
            p.rmdir()
            
    monkeypatch.setattr(cleaner.app_remnants, "send2trash", mock_send2trash)
    
    # Test uninstall - real
    res_real = uninstall_app("TestApp", dry_run=False)
    assert res_real["app_removed"] is True
    assert res_real["leftovers"]["deleted"] == 2
    assert not mock_app_dir.exists()
    assert not sup_file.exists()
    assert not pref_file.exists()
