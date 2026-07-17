"""
py2app setup script for Mac Cleaner.
Builds a native macOS .app bundle.

Usage:
    python3 setup.py py2app -A        # Development (alias) build
    python3 setup.py py2app           # Standalone build
"""
import sys
from pathlib import Path
from setuptools import setup

# Ensure local packages are findable
sys.path.insert(0, str(Path(__file__).parent))

APP_NAME = "Mac Cleaner"
VERSION = "1.0.0"

# Entry point
APP = ["main.py"]

# Include local packages and dependencies
OPTIONS = {
    "argv_emulation": True,
    "includes": [
        "rich",
        "rich.console",
        "rich.panel",
        "rich.table",
        "rich.progress",
        "rich.prompt",
        "rich.text",
        "rich.columns",
        "rich.box",
        "rich.markup",
        "pygments",
        "Foundation",
    ],
    "packages": [
        "scanner",
        "cleaner",
        "utils",
        "ui",
    ],
    "excludes": [
        "tkinter",
        "matplotlib",
        "numpy",
        "IPython",
        "jedi",
        "unittest",
        "pytest",
    ],
    "plist": {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "com.maccleaner.app",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
    },
}

setup(
    name=APP_NAME,
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
