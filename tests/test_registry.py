import pytest
from core.registry import REGISTRY, Category, Level, UnknownCategoryError, get


def test_get_known_category():
    cat = get("caches")
    assert cat.key == "caches"
    assert cat.level is Level.SAFE
    assert cat.via_trash is True
    assert cat.user_data is False


def test_get_unknown_category_raises():
    with pytest.raises(UnknownCategoryError):
        get("nonexistent_category")


def test_every_entry_has_explanation():
    for cat in REGISTRY.values():
        assert cat.explanation.strip(), f"{cat.key} has no explanation"


def test_irreversible_is_exactly_risky_non_trash():
    irreversible = {k for k, c in REGISTRY.items() if c.irreversible}
    assert irreversible == {"recents", "snapshots"}


def test_user_data_categories():
    user_data = {k for k, c in REGISTRY.items() if c.user_data}
    assert user_data == {"downloads", "ios_backups", "large_files"}


def test_non_trash_junk_is_not_irreversible():
    # brew/npm bypass Trash but are SAFE -> labeled, never gated
    assert REGISTRY["brew_cleanup"].via_trash is False
    assert REGISTRY["brew_cleanup"].irreversible is False
    assert REGISTRY["npm_cache"].irreversible is False


def test_all_cleaner_categories_registered():
    # every category any cleaner passes to safe_delete
    for key in [
        "caches", "logs", "temp", "downloads", "ios_backups", "large_files",
        "browser_cache", "browser_history", "tracking_data", "recents",
        "app_bundle", "app_leftovers", "launch_agents",
        "xcode_derived_data", "cocoapods_cache", "pip_cache",
        "brew_cleanup", "npm_cache", "snapshots",
    ]:
        assert key in REGISTRY
