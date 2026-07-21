#!/usr/bin/env python3
"""Mac Cleaner - entry point.

Default: the Rich interactive menu (cli/). Pass --tui (or --textual) to launch
the Textual full-screen UI instead, which is kept alongside.
"""
import sys


def main() -> None:
    flags = sys.argv[1:]
    if "--tui" in flags or "--textual" in flags:
        from ui.app import CleanerApp

        CleanerApp().run()
        return

    from cli.app import run

    run()


if __name__ == "__main__":
    main()
