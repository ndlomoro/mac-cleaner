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

import core.deleter as deleter_mod
from core.deleter import DeleteReport
from cleaner.optimization import clear_pip_cache


def test_clear_pip_cache_via_safe_delete(tmp_path, monkeypatch):
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir()

    def _fake(path):
        dest = trash_dir / path.name
        path.rename(dest)
        return dest

    monkeypatch.setattr(deleter_mod, "trash_item", _fake)
    monkeypatch.setattr(deleter_mod, "running_apps", lambda: {})

    pip_cache = tmp_path / "pip"
    pip_cache.mkdir()
    (pip_cache / "wheel.whl").write_bytes(b"x" * 10)
    monkeypatch.setattr("cleaner.optimization.PIP_CACHE", pip_cache)

    report = clear_pip_cache(dry_run=False)
    assert isinstance(report, DeleteReport)
    assert report.category == "pip_cache"
    assert not pip_cache.exists()


def test_clear_pip_cache_missing_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr("cleaner.optimization.PIP_CACHE", tmp_path / "nope")
    result = clear_pip_cache()
    assert result["skipped"] is True

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
