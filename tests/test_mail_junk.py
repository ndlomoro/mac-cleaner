from pathlib import Path

from scanner.mail_junk import _outside_mail_store, scan_mail_downloads, scan_mail_junk
from utils.helpers import HOME


def test_scans_download_dirs(tmp_path, monkeypatch):
    d = tmp_path / "Mail Downloads"
    (d / "invoice-copy").mkdir(parents=True)
    (d / "invoice-copy" / "invoice.pdf").write_bytes(b"x" * 50)
    (d / "photo.jpg").write_bytes(b"y" * 20)
    monkeypatch.setattr("scanner.mail_junk.MAIL_DOWNLOAD_DIRS", [d])
    result = scan_mail_downloads()
    assert result.category == "mail_downloads"
    assert result.file_count == 2
    assert result.total_size == 70


def test_never_emits_under_library_mail(tmp_path, monkeypatch):
    # A path under ~/Library/Mail need not exist on disk to be caught - the
    # guard is a structural (path-relative-to) check, not an existence
    # check. Exercise _outside_mail_store directly on a hypothetical
    # subpath so this test can't pass by short-circuiting on
    # root.exists() before the guard even runs.
    hypothetical = HOME / "Library" / "Mail" / "x"
    assert _outside_mail_store(hypothetical) is False

    inside = tmp_path / "Library" / "Mail" / "Downloads"
    inside.mkdir(parents=True)
    (inside / "f.bin").write_bytes(b"x")
    monkeypatch.setattr("scanner.mail_junk.HOME", tmp_path)
    monkeypatch.setattr("scanner.mail_junk.MAIL_DOWNLOAD_DIRS", [inside])
    assert scan_mail_downloads().file_count == 0  # guard vs monkeypatched HOME


def test_scan_mail_junk_returns_nonempty_results_only(tmp_path, monkeypatch):
    monkeypatch.setattr("scanner.mail_junk.MAIL_DOWNLOAD_DIRS", [tmp_path / "nope"])
    monkeypatch.setattr("scanner.mail_junk.MAIL_CACHE_DIRS", [tmp_path / "also-nope"])
    assert scan_mail_junk() == []


def test_outside_mail_store_allows_legacy_mail_downloads_sibling():
    # Pins the component-boundary guarantee: the legacy "Mail Downloads"
    # location is a SIBLING of ~/Library/Mail, not a child, so the guard
    # must treat it as outside the hard-protected Mail store.
    assert _outside_mail_store(HOME / "Library" / "Mail Downloads")
