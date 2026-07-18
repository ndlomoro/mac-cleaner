import json
import os
import time
from pathlib import Path

from scanner.dev_junk import find_docker_junk, find_project_artifacts, find_simulators


def _mtime(p: Path, days_ago: float) -> None:
    t = time.time() - days_ago * 86400
    os.utime(p, (t, t))


def _make_node_project(root: Path, name: str, src_days: float, nm_days: float) -> Path:
    proj = root / name
    (proj / "node_modules" / "left-pad").mkdir(parents=True)
    (proj / "node_modules" / "left-pad" / "index.js").write_bytes(b"x" * 100)
    (proj / "package.json").write_text("{}")
    (proj / "app.js").write_text("code")
    _mtime(proj / "app.js", src_days)
    _mtime(proj / "package.json", src_days)
    _mtime(proj / "node_modules" / "left-pad" / "index.js", nm_days)
    return proj


def test_detects_kinds_and_staleness(tmp_path, monkeypatch):
    monkeypatch.setattr("scanner.dev_junk.PROJECT_ROOTS", [tmp_path])
    proj = _make_node_project(tmp_path, "dead-app", src_days=200, nm_days=1)

    rust = tmp_path / "oxidized"
    (rust / "target" / "debug").mkdir(parents=True)
    (rust / "target" / "debug" / "bin").write_bytes(b"x" * 50)
    (rust / "Cargo.toml").write_text("[package]")
    (rust / "main.rs").write_text("fn main() {}")
    _mtime(rust / "main.rs", 3)

    venv_proj = tmp_path / "pyapp"
    (venv_proj / ".venv").mkdir(parents=True)
    (venv_proj / ".venv" / "pyvenv.cfg").write_text("home = /usr/bin")
    (venv_proj / "app.py").write_text("pass")
    _mtime(venv_proj / "app.py", 50)

    results = find_project_artifacts()
    by_kind = {r["kind"]: r for r in results}
    assert set(by_kind) == {"node_modules", "rust_target", "venv"}
    # staleness = project source age, NOT artifact age: node_modules touched
    # yesterday but sources 200d old -> stale
    assert by_kind["node_modules"]["age_days"] >= 199
    assert by_kind["rust_target"]["age_days"] <= 4
    assert by_kind["node_modules"]["project"] == "dead-app"
    assert by_kind["node_modules"]["size"] == 100


def test_never_descends_into_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("scanner.dev_junk.PROJECT_ROOTS", [tmp_path])
    proj = _make_node_project(tmp_path, "app", 10, 10)
    # a nested project INSIDE node_modules must not be reported
    inner = proj / "node_modules" / "dep"
    inner.mkdir()
    (inner / "package.json").write_text("{}")
    (inner / "node_modules").mkdir()
    results = find_project_artifacts()
    assert len([r for r in results if r["kind"] == "node_modules"]) == 1


def test_depth_cap(tmp_path, monkeypatch):
    monkeypatch.setattr("scanner.dev_junk.PROJECT_ROOTS", [tmp_path])
    monkeypatch.setattr("scanner.dev_junk.MAX_DEPTH", 2)
    deep = tmp_path / "a" / "b" / "c" / "d"
    (deep / "node_modules").mkdir(parents=True)
    (deep / "package.json").write_text("{}")
    assert find_project_artifacts() == []


def test_colocated_venv_does_not_contaminate_staleness(tmp_path, monkeypatch):
    monkeypatch.setattr("scanner.dev_junk.PROJECT_ROOTS", [tmp_path])
    proj = _make_node_project(tmp_path, "mixed", src_days=200, nm_days=1)
    (proj / ".venv").mkdir()
    (proj / ".venv" / "pyvenv.cfg").write_text("home = /usr/bin")  # fresh, 0d
    results = find_project_artifacts()
    by_kind = {r["kind"]: r for r in results}
    assert by_kind["node_modules"]["age_days"] >= 199  # venv freshness must not leak


def test_staleness_walk_never_enters_artifacts(tmp_path, monkeypatch):
    import os as os_mod
    monkeypatch.setattr("scanner.dev_junk.PROJECT_ROOTS", [tmp_path])
    _make_node_project(tmp_path, "app", 10, 10)
    visited = []
    real_walk = os_mod.walk
    def recording_walk(top, **kw):
        for t in real_walk(top, **kw):
            visited.append(t[0])
            yield t
    monkeypatch.setattr("scanner.dev_junk.os.walk", recording_walk, raising=False)
    find_project_artifacts()
    assert not any("node_modules" in v for v in visited)


def test_permission_denied_dir_does_not_crash_scan(tmp_path, monkeypatch):
    monkeypatch.setattr("scanner.dev_junk.PROJECT_ROOTS", [tmp_path])
    proj = _make_node_project(tmp_path, "app", 10, 10)
    locked = proj / "locked"
    locked.mkdir()
    (locked / "secret.txt").write_text("x")
    os.chmod(locked, 0o000)

    try:
        if os.access(locked, os.R_OK):
            # chmod-based denial doesn't reproduce under this test user
            # (e.g. running as root, which ignores mode bits) - force the
            # PermissionError path deterministically instead.
            import scanner.dev_junk as dj
            real_exists = Path.exists

            def fake_exists(self, *a, **kw):
                if self == locked / "pyvenv.cfg":
                    raise PermissionError("simulated for test")
                return real_exists(self, *a, **kw)

            monkeypatch.setattr(dj.Path, "exists", fake_exists)

        results = find_project_artifacts()
    finally:
        os.chmod(locked, 0o755)

    assert len([r for r in results if r["kind"] == "node_modules"]) == 1


def test_locked_venv_dir_does_not_crash_scan(tmp_path, monkeypatch):
    monkeypatch.setattr("scanner.dev_junk.PROJECT_ROOTS", [tmp_path])
    # a sibling, ordinary project - its artifacts must still surface even
    # though the locked-venv project below must not crash the whole scan
    _make_node_project(tmp_path, "other-app", 10, 10)

    proj = tmp_path / "pyapp"
    venv = proj / ".venv"
    venv.mkdir(parents=True)
    (venv / "pyvenv.cfg").write_text("home = /usr/bin")
    (proj / "app.py").write_text("pass")
    os.chmod(venv, 0o000)

    try:
        if os.access(venv, os.X_OK):
            # chmod-based denial doesn't reproduce under this test user
            # (e.g. running as root, which ignores mode bits) - force the
            # PermissionError path deterministically instead.
            import scanner.dev_junk as dj
            real_exists = Path.exists

            def fake_exists(self, *a, **kw):
                if self == venv / "pyvenv.cfg":
                    raise PermissionError("simulated for test")
                return real_exists(self, *a, **kw)

            monkeypatch.setattr(dj.Path, "exists", fake_exists)

        results = find_project_artifacts()  # must not raise
    finally:
        os.chmod(venv, 0o755)

    # the locked venv may or may not be reported, but the scan must complete
    # and the sibling project's artifacts must still show up
    assert any(r["kind"] == "node_modules" and r["project"] == "other-app" for r in results)


def test_cache_roots_have_no_fake_staleness(tmp_path, monkeypatch):
    # gradle_cache/maven_repo are shared cache roots, not tied to a single
    # project's sources - age_days must be None (never a real-looking
    # "900d idle" figure that would misrepresent staleness or let the row
    # float to the top of a stalest-first sort ahead of genuinely stale
    # projects).
    monkeypatch.setattr("scanner.dev_junk.PROJECT_ROOTS", [])
    gradle = tmp_path / "gradle-caches"
    gradle.mkdir()
    (gradle / "modules-2").write_bytes(b"x" * 10)
    maven = tmp_path / "m2-repo"
    maven.mkdir()
    (maven / "repository.jar").write_bytes(b"x" * 20)
    monkeypatch.setattr("scanner.dev_junk._CACHE_ROOTS", [
        ("gradle_cache", gradle), ("maven_repo", maven),
    ])
    results = find_project_artifacts()
    by_kind = {r["kind"]: r for r in results}
    assert set(by_kind) == {"gradle_cache", "maven_repo"}
    assert by_kind["gradle_cache"]["age_days"] is None
    assert by_kind["maven_repo"]["age_days"] is None


def test_stalest_first_sort_treats_none_age_as_zero_not_top(tmp_path, monkeypatch):
    monkeypatch.setattr("scanner.dev_junk.PROJECT_ROOTS", [tmp_path])
    _make_node_project(tmp_path, "dead-app", src_days=500, nm_days=1)
    cache = tmp_path / "gradle-caches"
    cache.mkdir()
    (cache / "modules-2").write_bytes(b"x" * 10)
    monkeypatch.setattr("scanner.dev_junk._CACHE_ROOTS", [("gradle_cache", cache)])
    results = find_project_artifacts()
    # stalest-first: the genuinely 500d-stale project must sort ahead of the
    # cache-root row, which has no real staleness signal (None -> 0).
    assert results[0]["kind"] == "node_modules"
    assert results[-1]["kind"] == "gradle_cache"


DOCKER_DF = "\n".join([
    '{"Type":"Images","Size":"10GB","Reclaimable":"8GB"}',
    '{"Type":"Local Volumes","Size":"2GB","Reclaimable":"2GB"}',
    '{"Type":"Build Cache","Size":"500MB","Reclaimable":"500MB"}',
])


def test_docker_junk_parses_df(monkeypatch):
    monkeypatch.setattr("scanner.dev_junk.run_command",
                        lambda cmd: (DOCKER_DF, "", 0))
    monkeypatch.setattr("scanner.dev_junk._which",
                        lambda name: "/usr/local/bin/docker")
    result = find_docker_junk()
    assert result["images_bytes"] == 8 * 1000**3
    assert result["volumes_bytes"] == 2 * 1000**3
    assert result["build_cache_bytes"] == 500 * 1000**2


def test_docker_absent_returns_none(monkeypatch):
    monkeypatch.setattr("scanner.dev_junk._which", lambda name: None)
    assert find_docker_junk() is None


DOCKER_DF_PCT = "\n".join([
    '{"Type":"Images","Size":"10GB","Reclaimable":"8GB"}',
    '{"Type":"Local Volumes","Size":"2GB","Reclaimable":"2GB"}',
    '{"Type":"Build Cache","Size":"500MB","Reclaimable":"1.5GB (50%)"}',
])


def test_docker_junk_parses_reclaimable_with_percentage_suffix(monkeypatch):
    monkeypatch.setattr("scanner.dev_junk.run_command",
                        lambda cmd: (DOCKER_DF_PCT, "", 0))
    monkeypatch.setattr("scanner.dev_junk._which",
                        lambda name: "/usr/local/bin/docker")
    result = find_docker_junk()
    assert result["build_cache_bytes"] == int(1.5 * 1000**3)


SIMCTL = json.dumps({"devices": {
    "com.apple.CoreSimulator.SimRuntime.iOS-15-0": [
        {"name": "iPhone 12", "isAvailable": False, "udid": "AAA", "state": "Shutdown"},
    ],
    "com.apple.CoreSimulator.SimRuntime.iOS-18-0": [
        {"name": "iPhone 16", "isAvailable": True, "udid": "BBB", "state": "Shutdown"},
    ],
}})


def test_simulators_lists_unavailable_only(monkeypatch):
    monkeypatch.setattr("scanner.dev_junk._which", lambda name: "/usr/bin/xcrun")
    monkeypatch.setattr("scanner.dev_junk.run_command", lambda cmd: (SIMCTL, "", 0))
    sims = find_simulators()
    assert [s["name"] for s in sims] == ["iPhone 12"]


def test_simulators_absent(monkeypatch):
    monkeypatch.setattr("scanner.dev_junk._which", lambda name: None)
    assert find_simulators() == []


def test_docker_command_failure_returns_none(monkeypatch):
    monkeypatch.setattr("scanner.dev_junk._which", lambda name: "/usr/local/bin/docker")
    monkeypatch.setattr("scanner.dev_junk.run_command", lambda cmd: ("", "boom", 1))
    assert find_docker_junk() is None


def test_simulators_command_failure_returns_empty(monkeypatch):
    monkeypatch.setattr("scanner.dev_junk._which", lambda name: "/usr/bin/xcrun")
    monkeypatch.setattr("scanner.dev_junk.run_command", lambda cmd: ("", "boom", 1))
    assert find_simulators() == []


DOCKER_DF_BAD_SHAPE = "\n".join([
    '"just a string"',
    '{"Type":"Images","Size":"10GB","Reclaimable":"8GB"}',
])


def test_docker_junk_skips_non_dict_json_line(monkeypatch):
    monkeypatch.setattr("scanner.dev_junk.run_command",
                        lambda cmd: (DOCKER_DF_BAD_SHAPE, "", 0))
    monkeypatch.setattr("scanner.dev_junk._which",
                        lambda name: "/usr/local/bin/docker")
    result = find_docker_junk()
    assert result["images_bytes"] == 8 * 1000**3


DOCKER_DF_NULL_RECLAIMABLE = '{"Type":"Images","Size":"10GB","Reclaimable":null}'


def test_docker_junk_handles_null_reclaimable(monkeypatch):
    monkeypatch.setattr("scanner.dev_junk.run_command",
                        lambda cmd: (DOCKER_DF_NULL_RECLAIMABLE, "", 0))
    monkeypatch.setattr("scanner.dev_junk._which",
                        lambda name: "/usr/local/bin/docker")
    result = find_docker_junk()
    assert result["images_bytes"] == 0


def test_simulators_handles_devices_wrong_shape(monkeypatch):
    monkeypatch.setattr("scanner.dev_junk._which", lambda name: "/usr/bin/xcrun")
    monkeypatch.setattr("scanner.dev_junk.run_command",
                        lambda cmd: (json.dumps({"devices": []}), "", 0))
    assert find_simulators() == []
