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


def test_delete_from_trash_refuses_dotdot_escape(tmp_path):
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir()
    victim = tmp_path / "outside.txt"
    victim.write_text("keep me")
    sneaky = trash_dir / ".." / "outside.txt"
    with pytest.raises(NotInTrashError):
        delete_from_trash(sneaky)
    assert victim.exists()


def test_delete_from_trash_refuses_symlinked_ancestor(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / "v.txt"
    victim.write_text("keep me")
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir()
    link = trash_dir / "fake-subdir"
    link.symlink_to(outside)
    with pytest.raises(NotInTrashError):
        delete_from_trash(link / "v.txt")
    assert victim.exists()


def test_delete_from_trash_still_deletes_symlink_items(tmp_path):
    trash_dir = tmp_path / ".Trash"
    trash_dir.mkdir()
    target = tmp_path / "target.txt"
    target.write_text("data")
    link = trash_dir / "trashed-link"
    link.symlink_to(target)
    delete_from_trash(link)
    assert not link.is_symlink() and not link.exists()
    assert target.exists()  # only the link is removed, never its target
