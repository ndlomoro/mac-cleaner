"""CleanerApp - the Textual application shell. Screens are added by later tasks."""
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header


class CleanerApp(App):
    TITLE = "Mac Cleaner"
    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()
