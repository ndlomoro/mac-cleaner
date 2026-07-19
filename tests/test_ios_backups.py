import plistlib
from datetime import datetime, timedelta
from pathlib import Path

from scanner.ios_backups import scan_ios_backups


def _make_backup(root: Path, udid: str, plist: dict | bytes | None) -> Path:
    b = root / udid
    b.mkdir(parents=True)
    (b / "blob.bin").write_bytes(b"x" * 100)
    if plist is not None:
        target = b / "Info.plist"
        if isinstance(plist, bytes):
            target.write_bytes(plist)
        else:
            with open(target, "wb") as f:
                plistlib.dump(plist, f)
    return b


def test_parses_device_metadata_and_backup_age(tmp_path, monkeypatch):
    monkeypatch.setattr("scanner.ios_backups.BACKUP_ROOT", tmp_path)
    last = datetime.now() - timedelta(days=941)
    _make_backup(tmp_path, "aaaa1111", {
        "Device Name": "Nick's iPhone 11",
        "Product Version": "16.2",
        "Last Backup Date": last,
    })
    result = scan_ios_backups()
    assert result.category == "ios_backups"
    row = result.files[0]
    assert row["device_name"] == "Nick's iPhone 11"
    assert row["ios_version"] == "16.2"
    assert 939 <= row["age_days"] <= 943
    assert row["size"] >= 100


def test_missing_plist_falls_back_gracefully(tmp_path, monkeypatch):
    monkeypatch.setattr("scanner.ios_backups.BACKUP_ROOT", tmp_path)
    _make_backup(tmp_path, "bbbb2222", None)
    row = scan_ios_backups().files[0]
    assert row["device_name"] is None
    assert row["ios_version"] is None
    assert row["age_days"] >= 0  # mtime fallback
    assert row["path"].endswith("bbbb2222")


def test_corrupt_plist_and_missing_keys_never_raise(tmp_path, monkeypatch):
    monkeypatch.setattr("scanner.ios_backups.BACKUP_ROOT", tmp_path)
    _make_backup(tmp_path, "cccc3333", b"not a plist at all")
    _make_backup(tmp_path, "dddd4444", {"Product Version": "17.0"})  # no name, no date
    rows = {r["path"].rsplit("/", 1)[-1]: r for r in scan_ios_backups().files}
    assert rows["cccc3333"]["device_name"] is None
    assert rows["dddd4444"]["ios_version"] == "17.0"
    assert rows["dddd4444"]["device_name"] is None
    assert len(rows) == 2


def test_future_backup_date_clamps_to_zero(tmp_path, monkeypatch):
    monkeypatch.setattr("scanner.ios_backups.BACKUP_ROOT", tmp_path)
    _make_backup(tmp_path, "eeee5555", {
        "Last Backup Date": datetime.now() + timedelta(days=30),
    })
    assert scan_ios_backups().files[0]["age_days"] == 0


def test_truncated_xml_plist_does_not_kill_the_scan(tmp_path, monkeypatch):
    monkeypatch.setattr("scanner.ios_backups.BACKUP_ROOT", tmp_path)
    _make_backup(tmp_path, "ffff6666",
                 b'<?xml version="1.0"?><plist><string>unterminated')
    _make_backup(tmp_path, "gggg7777", {"Product Version": "18.0"})
    rows = {r["path"].rsplit("/", 1)[-1]: r for r in scan_ios_backups().files}
    assert len(rows) == 2
    assert rows["ffff6666"]["device_name"] is None
    assert rows["ffff6666"]["ios_version"] is None
    assert rows["gggg7777"]["ios_version"] == "18.0"
