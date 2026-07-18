from pathlib import Path

from scanner.mail_junk import scan_mail_downloads, scan_mail_junk


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
    fake_mail = Path.home() / "Library" / "Mail" / "V10-fake-test-subdir"
    # do NOT create it - configure the scanner AT a ~/Library/Mail path and
    # verify the structural guard refuses even if the dir existed; use a
    # tmp stand-in that IS created for the second assertion
    monkeypatch.setattr("scanner.mail_junk.MAIL_DOWNLOAD_DIRS", [fake_mail])
    assert scan_mail_downloads().file_count == 0

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
