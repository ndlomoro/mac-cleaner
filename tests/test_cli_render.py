import pytest

from cli import render
from cli.io import parse_row_selection
from core.deleter import DeleteReport, Outcome, PathResult
from core.registry import Level, get as get_category


def _report(category, dry_run, trashed=(), skipped=(), failed=()):
    r = DeleteReport(category=category, dry_run=dry_run)
    for path, size in trashed:
        r.results.append(PathResult(path, Outcome.TRASHED, size,
                                    trash_path="" if dry_run else f"/T/{path}"))
    for path, reason in skipped:
        r.results.append(PathResult(path, Outcome.SKIPPED, 0, reason))
    for path, reason in failed:
        r.results.append(PathResult(path, Outcome.FAILED, 0, reason))
    return r


# ---- report_lines: truthful wording (CONTEXT.md) ----

def test_report_lines_dry_run_says_would():
    lines = render.report_lines(_report("caches", True, trashed=[("/a", 100)]))
    assert lines[0] == "Would move to Trash: 1 item(s) (~100 B)"


def test_report_lines_real_says_moved_not_freed():
    lines = render.report_lines(_report("caches", False, trashed=[("/a", 100)]))
    assert lines[0].startswith("Moved to Trash: 1 item(s)")
    # Moving to the Trash is never "freed"/"Reclaimed".
    joined = " ".join(lines).lower()
    assert "freed" not in joined
    assert "reclaim" not in joined


def test_report_lines_lists_skips_and_failures():
    lines = render.report_lines(_report(
        "caches", False,
        trashed=[("/a", 5)],
        skipped=[("/proto/System", "hard-protected")],
        failed=[("/b", "permission denied")]))
    assert any("Skipped:" in ln and "hard-protected" in ln for ln in lines)
    assert any("Failed:" in ln and "permission denied" in ln for ln in lines)


def test_reports_lines_prefixes_category():
    reports = [_report("caches", False, trashed=[("/a", 5)]),
               _report("logs", False, trashed=[("/b", 6)])]
    lines = render.reports_lines(reports)
    assert any(ln.startswith("[caches]") for ln in lines)
    assert any(ln.startswith("[logs]") for ln in lines)


# ---- small pure renderers ----

def test_tail_truncates_with_ellipsis():
    assert render.tail("/short", 60) == "/short"
    long = "/" + "x" * 100
    out = render.tail(long, 20)
    assert out.startswith("…") and len(out) == 21


def test_category_header_flags_non_trash_categories():
    # snapshots is via_trash=False -> must warn it is not recoverable via Trash
    text = render.category_header(get_category("snapshots")).plain
    assert "[RISKY]" in text
    assert "not recoverable via Trash" in text


def test_level_tag_uses_level_value():
    assert render.level_tag(Level.SAFE).plain == "[SAFE]"


# ---- parse_row_selection ----

@pytest.mark.parametrize("text,expected", [
    ("", "back"), ("b", "back"), ("back", "back"),
    ("a", "all"), ("all", "all"),
    ("2", {2}), ("1,3", {1, 3}), ("1 3", {1, 3}),
    ("1-3", {1, 2, 3}), ("1,3 5-6", {1, 3, 5, 6}),
])
def test_parse_row_selection_ok(text, expected):
    assert parse_row_selection(text, 10) == expected


@pytest.mark.parametrize("text", ["0", "11", "x", "3-1", "1,99"])
def test_parse_row_selection_rejects(text):
    with pytest.raises(ValueError):
        parse_row_selection(text, 10)
