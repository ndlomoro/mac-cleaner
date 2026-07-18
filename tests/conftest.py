"""Shared fixtures: fake trash + no running apps, for any test driving safe_delete."""
import pytest

import core.deleter as deleter_mod


@pytest.fixture
def no_running_apps(monkeypatch):
    monkeypatch.setattr(deleter_mod, "running_apps", lambda: {})


@pytest.fixture
def fake_trash(monkeypatch, tmp_path, no_running_apps):
    """Redirect trash_item into a fake .Trash dir; returns that dir."""
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir(exist_ok=True)

    def _fake(path):
        dest = trash_dir / path.name
        path.rename(dest)
        return dest

    monkeypatch.setattr(deleter_mod, "trash_item", _fake)
    return trash_dir
