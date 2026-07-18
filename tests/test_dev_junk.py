import os
import time
from pathlib import Path

from scanner.dev_junk import find_project_artifacts


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
