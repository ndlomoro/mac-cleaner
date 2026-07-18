from core.deleter import DeleteReport, Outcome, PathResult
from ui.widgets.category_header import header_markup
from ui.widgets.report_view import render_report


def test_header_markup_shows_level_and_explanation():
    text = header_markup("caches")
    assert "[green]" in text and "SAFE" in text
    assert "rebuild" in text  # from the registry explanation


def test_header_markup_labels_non_trash_categories():
    text = header_markup("brew_cleanup")
    assert "not recoverable via Trash" in text


def test_render_report_dry_and_real_wording():
    r = DeleteReport(category="caches", dry_run=True)
    r.results.append(PathResult("/tmp/x", Outcome.TRASHED, 123))
    r.results.append(PathResult("/tmp/y", Outcome.SKIPPED, 5, "Chrome is running"))
    out = render_report(r)
    assert "Would move to Trash" in out and "~123 B" in out
    assert "Chrome is running" in out
    assert "freed" not in out.lower()

    r2 = DeleteReport(category="caches", dry_run=False)
    r2.results.append(PathResult("/tmp/x", Outcome.FAILED, 1, "disk full"))
    out2 = render_report(r2)
    assert "Moved to Trash: 0" in out2 and "disk full" in out2
