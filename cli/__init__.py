"""Rich-based interactive menu UI (the primary interface).

`python main.py` launches cli.app.run(); the Textual TUI is kept reachable
via `python main.py --tui`. Everything here is a thin shell over the tested
core/scanner/cleaner packages - all deletion still goes through
core.deleter, and all user-facing wording follows CONTEXT.md.
"""
