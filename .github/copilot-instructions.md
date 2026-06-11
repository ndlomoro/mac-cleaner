# Copilot Instructions for Mac Cleaner

This file contains guidelines for AI assistants working in this repository.

## Build and Run Commands

- **Run directly**: `python3 main.py`
- **Development build**: `python3 setup.py py2app -A` (creates an alias build for quick testing)
- **Standalone build**: `python3 setup.py py2app` (creates a full `.app` bundle)
- *Note: There are currently no automated tests or linting frameworks configured for this repository.*

## High-Level Architecture

The application is a macOS system cleaner with a terminal-based user interface (TUI). 
The architecture strictly separates discovery and execution into two paired module directories:

1. **`scanner/`**: Modules here (e.g., `system_data.py`, `app_remnants.py`, `large_files.py`) are responsible solely for searching the filesystem, identifying target files/directories, and returning data structures representing what can be cleaned.
2. **`cleaner/`**: Modules here pair directly with `scanner` modules and contain the logic to safely delete or modify the items found.
3. **`ui/` and `main.py`**: The entry point is `main.py`, which orchestrates the scanners and cleaners while driving the TUI.
4. **`utils/`**: Contains shared infrastructure like OS-level command execution and path sizing.

## Key Conventions

- **TUI Rendering**: Use the `rich` library (Console, Table, Progress, Panel) for all terminal output. Avoid raw `print()` statements.
- **Path Manipulation**: Use `pathlib.Path` exclusively instead of `os.path` for all file system interactions.
- **Shell Commands**: Always use `utils.helpers.run_command` when executing external shell commands rather than calling `subprocess` directly. It includes built-in support for timeouts, error handling, and `sudo` escalation.
- **Dependency Management**: Standardize dependencies via `requirements.txt` and keep `excludes`/`includes` synced in `setup.py` when adding or removing packages to ensure `py2app` bundles correctly.
