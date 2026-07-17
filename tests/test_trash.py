from pathlib import Path

import pytest

from core.trash import NotInTrashError, TrashError, delete_from_trash, trash_item


def test_trash_roundtrip_and_surgical_delete(tmp_path):
    """Integration: really trash a file, get its Trash location, permanently delete it."""
    victim = tmp_path / "mac-cleaner-test-victim.txt"
    victim.write_text("delete me")

    trash_path = trash_item(victim)

    assert not victim.exists()
    assert trash_path.exists()
    assert any(part in (".Trash", ".Trashes") for part in trash_path.parts)

    delete_from_trash(trash_path)
    assert not trash_path.exists()


def test_trash_missing_file_raises(tmp_path):
    with pytest.raises(TrashError):
        trash_item(tmp_path / "never-existed.txt")


def test_delete_from_trash_refuses_paths_outside_trash(tmp_path):
    innocent = tmp_path / "innocent.txt"
    innocent.write_text("keep me")
    with pytest.raises(NotInTrashError):
        delete_from_trash(innocent)
    assert innocent.exists()
