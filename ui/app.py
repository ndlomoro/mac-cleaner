"""CleanerApp - the Textual application."""
from textual.app import App

from ui.screens.dashboard import DashboardScreen
from ui.screens.dev_junk import DevJunkScreen
from ui.screens.junk import JunkScreen
from ui.screens.optimize import OptimizeScreen
from ui.screens.privacy import PrivacyScreen
from ui.screens.snapshots import SnapshotsScreen
from ui.screens.space_finder import SpaceFinderScreen
from ui.screens.uninstall import UninstallScreen


class CleanerApp(App):
    TITLE = "Mac Cleaner"
    BINDINGS = [("q", "quit", "Quit")]
    SCREENS = {
        "junk": JunkScreen,
        "space_finder": SpaceFinderScreen,
        "privacy": PrivacyScreen,
        "optimize": OptimizeScreen,
        "snapshots": SnapshotsScreen,
        "uninstall": UninstallScreen,
        "dev_junk": DevJunkScreen,
    }

    def on_mount(self) -> None:
        self.push_screen(DashboardScreen())
