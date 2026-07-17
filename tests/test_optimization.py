import pytest
from pathlib import Path
import scanner.optimization
import cleaner.optimization
from scanner.optimization import check_launch_agents
from cleaner.optimization import (
    optimize_mac,
    run_brew_cleanup,
    run_periodic_scripts,
    clear_xcode_derived_data,
    clear_cocoapods_cache,
    clear_npm_cache,
    clear_pip_cache,
)

def test_check_launch_agents(tmp_path, monkeypatch):
    # Setup mock launch agent plist files
    user_la = tmp_path / "Library" / "LaunchAgents"
    user_la.mkdir(parents=True)
    (user_la / "com.test.agent.plist").write_text("plist content")
    
    # Mock Path constructor and .home() method
    original_path = Path
    def mock_path(*args, **kwargs):
        if len(args) > 0 and args[0] == "/Library/LaunchAgents":
            return tmp_path / "system_la"
        if len(args) > 0 and args[0] == "/Library/LaunchDaemons":
            return tmp_path / "system_ld"
        return original_path(*args, **kwargs)
    mock_path.home = lambda: tmp_path
    
    monkeypatch.setattr(scanner.optimization, "Path", mock_path)
    
    # Verify that check_launch_agents lists user agents
    agents = check_launch_agents()
    assert isinstance(agents, list)
    assert len(agents) == 1
    assert agents[0]["name"] == "com.test.agent"


def test_run_brew_cleanup(monkeypatch):
    # Mock brew exists but fails/skips
    monkeypatch.setattr(cleaner.optimization, "run_command", lambda cmd: ("", "", 1))
    res = run_brew_cleanup()
    assert res["skipped"] is True
    
    # Mock brew exists and succeeds
    monkeypatch.setattr(cleaner.optimization, "run_command", lambda cmd: ("cleaned 10MB", "", 0) if cmd[0] == "brew" else ("", "", 0))
    res2 = run_brew_cleanup(dry_run=False)
    assert "complete" in res2["message"]
    assert res2["output"] == "cleaned 10MB"

def test_run_periodic_scripts(monkeypatch):
    monkeypatch.setattr(cleaner.optimization, "run_command", lambda cmd, sudo=False: ("periodic success", "", 0))
    res = run_periodic_scripts(dry_run=False)
    assert res["periodic_scripts"]["daily"]["success"] is True

def test_clear_caches(tmp_path, monkeypatch):
    # Xcode derived data
    derived_dir = tmp_path / "Library" / "Developer" / "Xcode" / "DerivedData"
    derived_dir.mkdir(parents=True)
    (derived_dir / "build_cache").write_bytes(b"x" * 100)
    
    # CocoaPods cache
    pods_dir = tmp_path / ".cocoapods"
    pods_dir.mkdir()
    (pods_dir / "cache_file").write_bytes(b"y" * 200)
    
    # pip cache
    pip_dir = tmp_path / "Library" / "Caches" / "pip"
    pip_dir.mkdir(parents=True)
    (pip_dir / "pip_cache_file").write_bytes(b"z" * 300)
    
    # Mock home
    monkeypatch.setattr(cleaner.optimization.Path, "home", lambda: tmp_path)
    
    # Dry run check
    res_xcode_dry = clear_xcode_derived_data(dry_run=True)
    assert res_xcode_dry["dry_run"] is True
    assert res_xcode_dry["size"] == 100
    
    res_pods_dry = clear_cocoapods_cache(dry_run=True)
    assert res_pods_dry["dry_run"] is True
    assert res_pods_dry["size"] == 200
    
    res_pip_dry = clear_pip_cache(dry_run=True)
    assert res_pip_dry["dry_run"] is True
    assert res_pip_dry["size"] == 300
    
    # Mock send2trash to delete
    def mock_send2trash(path):
        p = Path(path)
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            [f.unlink() for f in p.rglob("*") if f.is_file()]
            p.rmdir()
            
    monkeypatch.setattr(cleaner.optimization, "send2trash", mock_send2trash)
    
    # Actual cleanup
    res_xcode_real = clear_xcode_derived_data(dry_run=False)
    assert res_xcode_real["freed"] == 100
    assert not derived_dir.exists()
    
    res_pods_real = clear_cocoapods_cache(dry_run=False)
    assert res_pods_real["freed"] == 200
    assert not pods_dir.exists()
    
    res_pip_real = clear_pip_cache(dry_run=False)
    assert res_pip_real["freed"] == 300
    assert not pip_dir.exists()

def test_optimize_mac_full(monkeypatch):
    # Mock check_launch_agents
    monkeypatch.setattr(cleaner.optimization, "check_launch_agents", lambda: [])
    # Mock each clear/cleanup sub-function
    monkeypatch.setattr(cleaner.optimization, "run_brew_cleanup", lambda dry_run: {"message": "brew info"})
    monkeypatch.setattr(cleaner.optimization, "clear_xcode_derived_data", lambda dry_run: {"message": "xcode info"})
    monkeypatch.setattr(cleaner.optimization, "clear_cocoapods_cache", lambda dry_run: {"message": "pods info"})
    monkeypatch.setattr(cleaner.optimization, "clear_npm_cache", lambda dry_run: {"message": "npm info"})
    monkeypatch.setattr(cleaner.optimization, "clear_pip_cache", lambda dry_run: {"message": "pip info"})
    
    res = optimize_mac(dry_run=True)
    assert res["launch_agents"]["count"] == 0
    assert res["brew_cleanup"]["message"] == "brew info"
