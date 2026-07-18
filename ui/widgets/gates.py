"""Gate modals - the only confirmation implementations in the UI.

ConfirmModal: y/N for trashing user-selected items (recoverable).
TypedGateModal: literal 'yes' for Irreversible Actions (not recoverable).
"""
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [("escape", "dismiss(False)", "Cancel")]
    DEFAULT_CSS = """
    ConfirmModal { align: center middle; }
    ConfirmModal #gate-box { width: 60; height: auto; border: thick $warning; padding: 1 2; }
    """

    def __init__(self, prompt: str, confirm_label: str = "Move to Trash",
                 decline_label: str = "Cancel") -> None:
        super().__init__()
        self.prompt = prompt
        self.confirm_label = confirm_label
        self.decline_label = decline_label

    def compose(self) -> ComposeResult:
        with Vertical(id="gate-box"):
            yield Label(self.prompt)
            with Horizontal():
                yield Button(self.decline_label, variant="primary", id="cancel")
                yield Button(self.confirm_label, variant="warning", id="confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")


class TypedGateModal(ModalScreen[bool]):
    BINDINGS = [("escape", "dismiss(False)", "Cancel")]
    DEFAULT_CSS = """
    TypedGateModal { align: center middle; }
    TypedGateModal #gate-box { width: 60; height: auto; border: thick $error; padding: 1 2; }
    """

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="gate-box"):
            yield Label(f"[bold red]{self.prompt}[/bold red]")
            yield Label("This cannot be undone. Type 'yes' to proceed:")
            yield Input(placeholder="no", id="gate-input")
            yield Button("Cancel", variant="primary", id="cancel")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip().lower() == "yes")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(False)
