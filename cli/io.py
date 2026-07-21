"""Terminal I/O primitives for the CLI.

Everything the flows need to talk to the user goes through the `UI` class, so
flows can be driven in tests by a stand-in with the same methods (no real
stdin). The two gates mirror the Textual widgets they replace:

    confirm()    - y/N, for Trashing recoverable items (ConfirmModal)
    typed_gate() - literal "yes", for Irreversible Actions (TypedGateModal)
"""
from rich.console import Console
from rich.prompt import Confirm, Prompt


def parse_row_selection(text: str, count: int) -> "str | set[int]":
    """Parse a row-selection string against `count` numbered rows (1..count).

    Returns "back" (empty or 'b'/'back'), "all" ('a'/'all'), or a set of
    1-based row numbers. Accepts comma/space separated numbers and N-M
    ranges (e.g. "1,3 5-7"). Raises ValueError on any unparseable or
    out-of-range token, so the caller can re-prompt instead of acting on a
    misread selection.
    """
    s = text.strip().lower()
    if s in ("", "b", "back"):
        return "back"
    if s in ("a", "all"):
        return "all"
    picked: set[int] = set()
    for token in s.replace(",", " ").split():
        if "-" in token.strip("-"):
            lo, hi = token.split("-", 1)
            lo_i, hi_i = int(lo), int(hi)
            if lo_i > hi_i:
                raise ValueError(f"descending range: {token}")
            picked.update(range(lo_i, hi_i + 1))
        else:
            picked.add(int(token))
    if not picked:
        raise ValueError("no rows given")
    for n in picked:
        if n < 1 or n > count:
            raise ValueError(f"row {n} is out of range 1..{count}")
    return picked


class UI:
    """Rich-backed console wrapper. Inject a Console for tests/redirection."""

    def __init__(self, console: "Console | None" = None) -> None:
        self.console = console or Console()

    # ---- output ----

    def print(self, renderable: object = "") -> None:
        self.console.print(renderable)

    def lines(self, lines: list[str]) -> None:
        for line in lines:
            self.console.print(line)

    def rule(self, title: str = "") -> None:
        self.console.rule(title)

    def notify(self, message: str) -> None:
        self.console.print(message)

    # ---- input ----

    def choose(self, prompt: str, choices: list[str]) -> str:
        """Prompt for one of `choices` (case-insensitive), re-asking until valid."""
        answer = Prompt.ask(prompt, choices=choices, show_choices=False,
                            console=self.console)
        return answer.strip().lower()

    def ask(self, prompt: str, default: str = "") -> str:
        return Prompt.ask(prompt, default=default, console=self.console).strip()

    def confirm(self, message: str) -> bool:
        """y/N gate for Trashing recoverable items. Defaults to No."""
        return Confirm.ask(message, default=False, console=self.console)

    def typed_gate(self, message: str) -> bool:
        """Typed 'yes' gate for Irreversible Actions. Anything else declines."""
        self.console.print(f"[bold red]{message}[/bold red]")
        answer = Prompt.ask("This cannot be undone. Type 'yes' to proceed",
                            default="no", console=self.console)
        return answer.strip().lower() == "yes"

    def pause(self) -> None:
        Prompt.ask("[dim]Press Enter to continue[/dim]", default="",
                   console=self.console)
