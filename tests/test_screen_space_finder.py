import asyncio
import time

from textual.app import App
from textual.widgets import SelectionList, Static

import cleaner.large_files as large_files_mod
import scanner.duplicates as duplicates_mod
from core.deleter import DeleteReport
from scanner.large_files import LargeFile
from scanner.system_data import ScanResult
from ui.app import CleanerApp
from ui.screens import space_finder as sf_mod
from ui.screens.space_finder import SpaceFinderScreen, _row_label
from ui.widgets.gates import ConfirmModal
from utils.helpers import format_size


def _make_dup_groups(monkeypatch, canon_dir, other_dir):
    """Build two duplicate groups whose keepers are deterministic: each
    group's designated keeper file lives under canon_dir (monkeypatched onto
    CANONICAL_DIRS), every other copy lives under other_dir - so pick_keeper's
    first tie-break tier (canonical location) decides the winner regardless
    of mtime/lexicographic ordering.

    Returns (groups, keeper_paths) where keeper_paths is the set of the two
    designated-keeper absolute path strings.
    """
    monkeypatch.setattr(duplicates_mod, "CANONICAL_DIRS", [canon_dir])
    g1_keep = canon_dir / "g1_keep.jpg"; g1_keep.write_bytes(b"1111")
    g1_dupe = other_dir / "g1_dupe.jpg"; g1_dupe.write_bytes(b"1111")
    g2_keep = canon_dir / "g2_keep.jpg"; g2_keep.write_bytes(b"2222")
    g2_dupe1 = other_dir / "g2_dupe1.jpg"; g2_dupe1.write_bytes(b"2222")
    g2_dupe2 = other_dir / "g2_dupe2.jpg"; g2_dupe2.write_bytes(b"2222")
    groups = [
        {"hash": "h1", "size": 4, "files": [str(g1_keep), str(g1_dupe)],
         "wasted": 4},
        {"hash": "h2", "size": 4,
         "files": [str(g2_keep), str(g2_dupe1), str(g2_dupe2)], "wasted": 8},
    ]
    keeper_paths = {str(g1_keep), str(g2_keep)}
    return groups, keeper_paths


class Host(App):
    def on_mount(self):
        self.push_screen(SpaceFinderScreen())


def _patch_scanners(monkeypatch, tmp_path, dup_paths=()):
    dl = ScanResult("downloads", "Downloads")
    f = tmp_path / "old.dmg"
    f.write_bytes(b"x" * 10)
    dl.add_file(str(f), 10, 400)
    monkeypatch.setattr("ui.screens.space_finder.scan_space_finder", lambda: [dl])
    monkeypatch.setattr("ui.screens.space_finder.find_large_files",
                        lambda **kw: [])
    groups = []
    if dup_paths:
        groups = [{"hash": "h1", "size": 4,
                   "files": [str(p) for p in dup_paths],
                   "wasted": 4 * (len(dup_paths) - 1)}]
    monkeypatch.setattr("ui.screens.space_finder.find_duplicates",
                        lambda **kw: groups)
    return f


async def test_nothing_preselected_and_no_select_all(tmp_path, monkeypatch, fake_trash):
    _patch_scanners(monkeypatch, tmp_path)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        for sl in host.screen.query(SelectionList):
            assert sl.selected == []
        bound_keys = {b[0] if isinstance(b, tuple) else b.key
                      for b in host.screen.BINDINGS}
        assert "a" not in bound_keys  # no select-all affordance


async def test_pick_confirm_trash(tmp_path, monkeypatch, fake_trash):
    f = _patch_scanners(monkeypatch, tmp_path)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        dl_list = host.screen.query_one("#list-downloads", SelectionList)
        dl_list.focus()
        await pilot.press("space")     # select the only row
        await pilot.press("t")         # Move to Trash -> ConfirmModal
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()
        assert not f.exists()
        assert (fake_trash / "old.dmg").exists()

        # Reclaim offer (parity with Junk screen): decline -> file stays in Trash
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert (fake_trash / "old.dmg").exists()


async def test_pick_confirm_trash_then_reclaim_confirmed(tmp_path, monkeypatch, fake_trash):
    f = _patch_scanners(monkeypatch, tmp_path)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        dl_list = host.screen.query_one("#list-downloads", SelectionList)
        dl_list.focus()
        await pilot.press("space")
        await pilot.press("t")
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()
        assert not f.exists()
        assert (fake_trash / "old.dmg").exists()

        # Reclaim offer: confirm by typing yes -> permanently gone
        await pilot.pause()
        for ch in "yes":
            await pilot.press(ch)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        assert not (fake_trash / "old.dmg").exists()


async def test_decline_leaves_everything(tmp_path, monkeypatch, fake_trash):
    f = _patch_scanners(monkeypatch, tmp_path)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        host.screen.query_one("#list-downloads", SelectionList).focus()
        await pilot.press("space", "t")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert f.exists()


async def test_skipped_items_stay_listed(tmp_path, monkeypatch, fake_trash):
    from pathlib import Path as P

    from scanner.system_data import ScanResult
    dl = ScanResult("downloads", "Downloads")
    good = tmp_path / "old.dmg"; good.write_bytes(b"x" * 10)
    # hard-protected -> SKIPPED. A nonexistent name under ~/.ssh, not the
    # developer's real key: is_protected() runs before any existence check,
    # so the protection assertion still holds without risking the real
    # ~/.ssh/id_ed25519 if this protection ever regresses.
    hard = P.home() / ".ssh" / "mac-cleaner-test-nonexistent-key"
    dl.add_file(str(good), 10, 400)
    dl.add_file(str(hard), 5, 900)
    monkeypatch.setattr("ui.screens.space_finder.scan_space_finder", lambda: [dl])
    monkeypatch.setattr("ui.screens.space_finder.find_large_files", lambda **kw: [])
    monkeypatch.setattr("ui.screens.space_finder.find_duplicates", lambda **kw: [])
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        sel = host.screen.query_one("#list-downloads", SelectionList)
        sel.select(0); sel.select(1)
        await pilot.press("t"); await pilot.pause()
        await pilot.click("#confirm"); await pilot.pause()
        await pilot.press("escape"); await pilot.pause()   # decline reclaim offer
        remaining = {it["path"] for it in host.screen.items["downloads"].values()}
        assert str(hard) in remaining          # skipped item still listed
        assert str(good) not in remaining      # trashed item removed


async def test_selected_total_footer_updates_and_resets(tmp_path, monkeypatch, fake_trash):
    f = _patch_scanners(monkeypatch, tmp_path)
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        footer = host.screen.query_one("#sel-total", Static)
        assert "Nothing selected" in footer.content

        dl_list = host.screen.query_one("#list-downloads", SelectionList)
        dl_list.focus()
        await pilot.press("space")     # select the only row (size=10)
        await pilot.pause()
        assert "1 item" in footer.content
        assert format_size(10) in footer.content

        await pilot.press("t")         # Move to Trash -> ConfirmModal
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()
        assert not f.exists()
        # selections were cleared by the trash pass - footer resets
        assert "Nothing selected" in footer.content


async def test_keep_one_invariant(tmp_path, monkeypatch, fake_trash):
    a = tmp_path / "a.jpg"; a.write_bytes(b"1234")
    b = tmp_path / "b.jpg"; b.write_bytes(b"1234")
    _patch_scanners(monkeypatch, tmp_path, dup_paths=(a, b))
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        dup_list = host.screen.query_one("#list-duplicates", SelectionList)
        dup_list.focus()
        await pilot.press("space")          # select copy 1 - fine
        await pilot.press("down", "space")  # try to select copy 2 - refused
        await pilot.pause()
        assert len(dup_list.selected) == 1  # one copy always kept


async def test_cross_tab_keep_one_enforced_via_large_files(
        tmp_path, monkeypatch, fake_trash):
    """Both copies of a duplicate group are also visible (and independently
    selectable) in the Large Files tab. Picking both there must be refused
    just like picking both directly in the Duplicates tab."""
    a = tmp_path / "a.jpg"; a.write_bytes(b"1234")
    b = tmp_path / "b.jpg"; b.write_bytes(b"1234")

    dl = ScanResult("downloads", "Downloads")
    monkeypatch.setattr("ui.screens.space_finder.scan_space_finder", lambda: [dl])
    monkeypatch.setattr(
        "ui.screens.space_finder.find_large_files",
        lambda **kw: [LargeFile(str(a), 4, 0), LargeFile(str(b), 4, 0)])
    groups = [{"hash": "h1", "size": 4, "files": [str(a), str(b)], "wasted": 4}]
    monkeypatch.setattr("ui.screens.space_finder.find_duplicates",
                        lambda **kw: groups)

    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        lf_list = host.screen.query_one("#list-large_files", SelectionList)
        lf_list.focus()
        await pilot.press("space")          # select copy 1 via Large Files
        await pilot.press("down", "space")  # select copy 2 via Large Files
        await pilot.pause()
        assert len(lf_list.selected) == 2   # this tab has no per-group guard

        await pilot.press("t")
        await pilot.pause()
        # refused before the ConfirmModal even appears - nothing was touched
        assert not isinstance(host.screen_stack[-1], ConfirmModal)
        assert a.exists()
        assert b.exists()


async def test_k_selects_exactly_non_keeper_indexes(tmp_path, monkeypatch, fake_trash):
    """(a) Nothing is pre-selected after scan; pressing k selects exactly the
    non-keeper rows across every duplicate group, never a keeper row."""
    canon_dir = tmp_path / "canon"; canon_dir.mkdir()
    other_dir = tmp_path / "other"; other_dir.mkdir()
    groups, keeper_paths = _make_dup_groups(monkeypatch, canon_dir, other_dir)

    dl = ScanResult("downloads", "Downloads")
    monkeypatch.setattr("ui.screens.space_finder.scan_space_finder", lambda: [dl])
    monkeypatch.setattr("ui.screens.space_finder.find_large_files", lambda **kw: [])
    monkeypatch.setattr("ui.screens.space_finder.find_duplicates", lambda **kw: groups)

    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        dup_list = host.screen.query_one("#list-duplicates", SelectionList)
        assert dup_list.selected == []  # nothing pre-selected after scan

        dup_list.focus()
        await pilot.press("k")
        await pilot.pause()

        items = host.screen.items["duplicates"]
        expected = {i for i, it in items.items() if it["path"] != it["keeper"]}
        assert set(dup_list.selected) == expected
        selected_paths = {items[i]["path"] for i in dup_list.selected}
        assert not (selected_paths & keeper_paths)  # keeper never selected

        # ★ badge renders only for the keeper row of each group
        for i, it in items.items():
            label = str(dup_list.get_option_at_index(i).prompt)
            if it["path"] in keeper_paths:
                assert label.startswith("★ keep")
            else:
                assert not label.startswith("★ keep")


async def test_k_then_trash_keepers_survive(tmp_path, monkeypatch, fake_trash):
    """(b) k then t -> confirm: keepers survive on disk, non-keepers land in
    the (fake) Trash."""
    canon_dir = tmp_path / "canon"; canon_dir.mkdir()
    other_dir = tmp_path / "other"; other_dir.mkdir()
    groups, keeper_paths = _make_dup_groups(monkeypatch, canon_dir, other_dir)
    all_paths = {p for g in groups for p in g["files"]}
    non_keeper_paths = all_paths - keeper_paths

    dl = ScanResult("downloads", "Downloads")
    monkeypatch.setattr("ui.screens.space_finder.scan_space_finder", lambda: [dl])
    monkeypatch.setattr("ui.screens.space_finder.find_large_files", lambda **kw: [])
    monkeypatch.setattr("ui.screens.space_finder.find_duplicates", lambda **kw: groups)

    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        dup_list = host.screen.query_one("#list-duplicates", SelectionList)
        dup_list.focus()
        await pilot.press("k")
        await pilot.press("t")
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()

        for p in keeper_paths:
            from pathlib import Path as P
            assert P(p).exists()
        for p in non_keeper_paths:
            from pathlib import Path as P
            assert not P(p).exists()
            assert (fake_trash / P(p).name).exists()

        # decline the reclaim offer, parity with the other trash-flow tests
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()


async def test_k_with_no_duplicates_notifies(tmp_path, monkeypatch, fake_trash):
    """(c) k with zero duplicate groups notifies "No duplicates found." and
    selects nothing anywhere."""
    _patch_scanners(monkeypatch, tmp_path)  # default: no dup_paths -> [] groups
    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        notifications = []
        host.screen.notify = lambda msg, **kw: notifications.append(
            (msg, kw.get("severity")))

        dup_list = host.screen.query_one("#list-duplicates", SelectionList)
        dup_list.focus()
        await pilot.press("k")
        await pilot.pause()

        assert any(msg == "No duplicates found." for msg, _ in notifications)
        for sl in host.screen.query(SelectionList):
            assert sl.selected == []


async def test_manual_select_after_k_still_keep_one_enforced(
        tmp_path, monkeypatch, fake_trash):
    """(d) explicit sequence: after k, manually trying to also select the
    keeper (which would leave zero copies of that group unselected) is still
    refused by the existing Keep-One handler - no regression from adding k."""
    canon_dir = tmp_path / "canon"; canon_dir.mkdir()
    other_dir = tmp_path / "other"; other_dir.mkdir()
    monkeypatch.setattr(duplicates_mod, "CANONICAL_DIRS", [canon_dir])
    keep = canon_dir / "keep.jpg"; keep.write_bytes(b"1234")
    dupe = other_dir / "dupe.jpg"; dupe.write_bytes(b"1234")
    groups = [{"hash": "h1", "size": 4, "files": [str(keep), str(dupe)],
               "wasted": 4}]

    dl = ScanResult("downloads", "Downloads")
    monkeypatch.setattr("ui.screens.space_finder.scan_space_finder", lambda: [dl])
    monkeypatch.setattr("ui.screens.space_finder.find_large_files", lambda **kw: [])
    monkeypatch.setattr("ui.screens.space_finder.find_duplicates", lambda **kw: groups)

    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        notifications = []
        host.screen.notify = lambda msg, **kw: notifications.append(
            (msg, kw.get("severity")))

        dup_list = host.screen.query_one("#list-duplicates", SelectionList)
        dup_list.focus()
        await pilot.press("k")
        await pilot.pause()
        assert len(dup_list.selected) == 1  # just the non-keeper (dupe)

        # find the keeper's option index and manually try to select it too
        items = host.screen.items["duplicates"]
        keeper_index = next(i for i, it in items.items()
                             if it["path"] == it["keeper"])
        dup_list.select(keeper_index)
        await pilot.pause()

        assert len(dup_list.selected) == 1  # still one copy always kept
        assert any("One copy of each duplicate is always kept" in msg
                   for msg, _ in notifications)


async def test_resume_during_slow_trash_does_not_rescan(tmp_path, monkeypatch, fake_trash):
    """Critical busy-coverage gap: the trash/reclaim flow never touched
    _scanning, so navigating away and back while safe_delete was still
    in-flight fired a resume-triggered _rescan() that raced _refresh_lists()
    and clobbered the just-trashed state. _trashing must span
    ConfirmModal -> trash worker -> (no reclaim offered here, single file)."""
    f = _patch_scanners(monkeypatch, tmp_path)

    rescan_calls = []
    real_rescan = sf_mod.SpaceFinderScreen._rescan

    def counting_rescan(self):
        rescan_calls.append(1)
        real_rescan(self)

    monkeypatch.setattr(sf_mod.SpaceFinderScreen, "_rescan", counting_rescan)

    real_safe_delete = sf_mod.safe_delete

    def slow_safe_delete(*args, **kwargs):
        time.sleep(0.3)
        return real_safe_delete(*args, **kwargs)

    monkeypatch.setattr("ui.screens.space_finder.safe_delete", slow_safe_delete)

    app = CleanerApp()
    async with app.run_test() as pilot:
        await pilot.press("2")
        await pilot.pause()                  # initial mount -> _rescan call #1
        dl_list = app.screen.query_one("#list-downloads", SelectionList)
        dl_list.focus()
        await pilot.press("space")
        await pilot.press("t")
        await pilot.pause()
        await pilot.click("#confirm")        # starts the 0.3s-slow trash worker
        await pilot.press("escape")          # navigate away mid-flight
        await pilot.pause()
        await pilot.press("2")               # re-enter mid-flight - must NOT rescan
        await pilot.pause()
        await asyncio.sleep(0.4)             # let the slow worker land
        await pilot.pause()
        await pilot.pause()
        # something was trashed, so the reclaim gate is now on top of the
        # stack - the SpaceFinderScreen itself lives one level down
        sf_screen = app.screen_stack[-2]
        assert sf_screen.query_one("#list-downloads", SelectionList).option_count == 0
        await pilot.press("escape")          # decline the reclaim gate

    assert rescan_calls == [1]                # only the initial on_mount rescan
    assert not f.exists()
    assert (fake_trash / "old.dmg").exists()


async def test_large_files_route_through_clean_large_files(tmp_path, monkeypatch):
    """The trash pass must split per category: large_files rows go through
    clean_large_files (which stamps user_selected=True itself), while every
    other category keeps calling safe_delete directly."""
    dl = ScanResult("downloads", "Downloads")
    dl_file = tmp_path / "old.dmg"
    dl_file.write_bytes(b"x" * 10)
    dl.add_file(str(dl_file), 10, 400)
    monkeypatch.setattr("ui.screens.space_finder.scan_space_finder", lambda: [dl])

    lf_file = tmp_path / "big.mov"
    lf_file.write_bytes(b"y" * 20)
    monkeypatch.setattr(
        "ui.screens.space_finder.find_large_files",
        lambda **kw: [LargeFile(str(lf_file), 20, 0)])
    monkeypatch.setattr("ui.screens.space_finder.find_duplicates", lambda **kw: [])

    clean_calls = []

    def fake_clean_large_files(paths, dry_run=False):
        clean_calls.append(list(paths))
        return DeleteReport("large_files", dry_run=False)

    monkeypatch.setattr(
        "ui.screens.space_finder.clean_large_files", fake_clean_large_files)

    safe_delete_calls = []

    def fake_safe_delete(rows, category, dry_run=False, user_selected=False):
        safe_delete_calls.append(category)
        return DeleteReport(category, dry_run=dry_run)

    monkeypatch.setattr("ui.screens.space_finder.safe_delete", fake_safe_delete)

    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        dl_list = host.screen.query_one("#list-downloads", SelectionList)
        dl_list.focus()
        await pilot.press("space")
        lf_list = host.screen.query_one("#list-large_files", SelectionList)
        lf_list.focus()
        await pilot.press("space")
        await pilot.press("t")
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()

    assert clean_calls == [[str(lf_file)]]
    assert safe_delete_calls == ["downloads"]


def test_row_label_enriched_ios_with_version():
    item = {"path": "/x", "size": 1234, "age_days": 5,
            "device_name": "Nick's iPhone", "ios_version": "17.4"}
    label = _row_label("ios_backups", item)
    assert "since backup" in label
    assert "Nick's iPhone" in label
    assert "(iOS 17.4)" in label
    assert "…/x" in label


def test_row_label_enriched_ios_without_version():
    item = {"path": "/x", "size": 1234, "age_days": 5,
            "device_name": "Nick's iPhone", "ios_version": None}
    label = _row_label("ios_backups", item)
    assert "since backup" in label
    assert "Nick's iPhone" in label
    assert "(iOS" not in label
    assert "…/x" in label


def test_row_label_enriched_same_device_name_distinguishable_by_path():
    # Two backups from devices sharing a display name (reset-and-repaired,
    # or two phones the user happened to name the same) must not render
    # identical labels - the path tail is what tells them apart.
    item_a = {"path": "/Users/x/MobileSync/Backup/AAAA", "size": 1234,
              "age_days": 5, "device_name": "iPhone", "ios_version": "17.4"}
    item_b = {"path": "/Users/x/MobileSync/Backup/BBBB", "size": 1234,
              "age_days": 5, "device_name": "iPhone", "ios_version": "17.4"}
    assert _row_label("ios_backups", item_a) != _row_label("ios_backups", item_b)


def test_row_label_generic_for_metadata_less_ios_row():
    item = {"path": "/some/path/backup-uuid", "size": 1234, "age_days": 5,
            "device_name": None, "ios_version": None}
    label = _row_label("ios_backups", item)
    assert "since backup" not in label
    assert label == _row_label("downloads", {**item})


def test_row_label_duplicates_keeper_badge():
    keeper_item = {"path": "/a", "size": 1234, "age_days": 5, "keeper": "/a"}
    other_item = {"path": "/b", "size": 1234, "age_days": 5, "keeper": "/a"}
    keeper_label = _row_label("duplicates", keeper_item)
    other_label = _row_label("duplicates", other_item)
    assert keeper_label.startswith("★ keep")
    assert not other_label.startswith("★ keep")
    # non-duplicates categories are unaffected by the "keeper" key
    assert not _row_label("downloads", keeper_item).startswith("★ keep")


async def test_ios_backup_rows_show_device_and_staleness(
        tmp_path, monkeypatch, fake_trash):
    """Pilot test: an enriched iOS row (device_name set) renders the
    device/staleness label; a metadata-less row keeps the generic form."""
    dl = ScanResult("downloads", "Downloads")
    ios = ScanResult("ios_backups", "iOS Backups")
    enriched = tmp_path / "00008030-enriched"
    ios.add_file(str(enriched), 5_000_000, 3)
    ios.files[-1]["device_name"] = "Nick's iPhone"
    ios.files[-1]["ios_version"] = "17.4"
    plain = tmp_path / "00008030-plain"
    ios.add_file(str(plain), 3_000_000, 9)
    ios.files[-1]["device_name"] = None
    ios.files[-1]["ios_version"] = None

    monkeypatch.setattr("ui.screens.space_finder.scan_space_finder",
                        lambda: [dl, ios])
    monkeypatch.setattr("ui.screens.space_finder.find_large_files",
                        lambda **kw: [])
    monkeypatch.setattr("ui.screens.space_finder.find_duplicates",
                        lambda **kw: [])

    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        sel = host.screen.query_one("#list-ios_backups", SelectionList)
        enriched_label = str(sel.get_option_at_index(0).prompt)
        plain_label = str(sel.get_option_at_index(1).prompt)
        assert "since backup" in enriched_label
        assert "Nick's iPhone" in enriched_label
        assert f"…{str(enriched)[-40:]}" in enriched_label
        assert "since backup" not in plain_label
        assert f"…{str(plain)[-70:]}" in plain_label


async def test_large_files_tab_real_clean_large_files_lands_in_trash(
        tmp_path, monkeypatch, fake_trash):
    """Integration variant: real clean_large_files (not mocked), driven
    through the conftest fake_trash - a real tmp file picked in the Large
    Files tab lands in the fake trash and the report's category is
    'large_files'."""
    dl = ScanResult("downloads", "Downloads")
    monkeypatch.setattr("ui.screens.space_finder.scan_space_finder", lambda: [dl])

    lf_file = tmp_path / "big.mov"
    lf_file.write_bytes(b"y" * 20)
    monkeypatch.setattr(
        "ui.screens.space_finder.find_large_files",
        lambda **kw: [LargeFile(str(lf_file), 20, 0)])
    monkeypatch.setattr("ui.screens.space_finder.find_duplicates", lambda **kw: [])

    captured_reports = []
    real_clean_large_files = large_files_mod.clean_large_files

    def wrapped_clean_large_files(paths, dry_run=False):
        report = real_clean_large_files(paths, dry_run=dry_run)
        captured_reports.append(report)
        return report

    monkeypatch.setattr(
        "ui.screens.space_finder.clean_large_files", wrapped_clean_large_files)

    host = Host()
    async with host.run_test() as pilot:
        await pilot.pause()
        lf_list = host.screen.query_one("#list-large_files", SelectionList)
        lf_list.focus()
        await pilot.press("space")
        await pilot.press("t")
        await pilot.pause()
        await pilot.click("#confirm")
        await pilot.pause()
        assert not lf_file.exists()
        assert (fake_trash / "big.mov").exists()

        # Decline the reclaim offer - parity with the other trash-flow tests.
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    assert len(captured_reports) == 1
    assert captured_reports[0].category == "large_files"
