from ui.app import CleanerApp


async def test_app_boots_and_quits():
    app = CleanerApp()
    async with app.run_test() as pilot:
        assert app.title == "Mac Cleaner"
        await pilot.press("q")
    assert app.return_value is None  # exited cleanly
