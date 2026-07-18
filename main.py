#!/usr/bin/env python3
"""Mac Cleaner - entry point. The UI lives in ui/ (Textual)."""


def main() -> None:
    from ui.app import CleanerApp

    CleanerApp().run()


if __name__ == "__main__":
    main()
