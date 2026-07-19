"""Category safety registry - every cleanable category must be declared here."""
from dataclasses import dataclass
from enum import Enum


class Level(str, Enum):
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    RISKY = "RISKY"


class UnknownCategoryError(KeyError):
    """Raised when a category is not declared in the registry."""


@dataclass(frozen=True)
class Category:
    key: str
    level: Level
    explanation: str
    user_data: bool = False   # True -> individual explicit selection required
    via_trash: bool = True    # False -> external tool / in-place mechanism

    @property
    def irreversible(self) -> bool:
        """Irreversible Action: RISKY and cannot go through the Trash. Gets the typed gate."""
        return not self.via_trash and self.level is Level.RISKY


_CATEGORIES = [
    Category("caches", Level.SAFE,
             "Temporary files apps rebuild automatically; first launches may be slower afterwards."),
    Category("logs", Level.SAFE,
             "Diagnostic text files apps write for troubleshooting; nothing reads them back."),
    Category("temp", Level.SAFE,
             "Leftover working files (*.tmp, *.bak, crash reports) no app will miss."),
    Category("browser_cache", Level.SAFE,
             "Saved copies of web pages; browsers re-download them, so pages load slower once."),
    Category("mail_downloads", Level.SAFE,
             "Copies of attachments you've opened in Mail. The originals stay in your mailboxes."),
    Category("mail_cache", Level.SAFE,
             "Mail's rebuildable caches; Mail recreates them on next launch."),
    Category("xcode_derived_data", Level.SAFE,
             "Xcode build products; the next build regenerates them from source."),
    Category("cocoapods_cache", Level.SAFE,
             "Downloaded CocoaPods packages; 'pod install' re-fetches what projects need."),
    Category("pip_cache", Level.SAFE,
             "Downloaded Python packages; pip re-fetches them on the next install."),
    Category("brew_cleanup", Level.SAFE,
             "Old Homebrew downloads and outdated versions; brew re-downloads on demand.",
             via_trash=False),
    Category("npm_cache", Level.SAFE,
             "Downloaded npm packages; npm re-fetches them on the next install.",
             via_trash=False),
    Category("app_bundle", Level.CAUTION,
             "The application itself; uninstalling removes it from /Applications."),
    Category("app_leftovers", Level.CAUTION,
             "Settings and support files left behind by an app; removing them resets the app."),
    Category("launch_agents", Level.CAUTION,
             "Programs set to run automatically at login; removing one stops that behavior."),
    Category("tracking_data", Level.RISKY,
             "Diagnostic reports and app tracking traces; may include data you'd rather keep private."),
    Category("browser_history", Level.RISKY,
             "Your browsing history; once cleared, it cannot be recovered from the browser."),
    Category("downloads", Level.RISKY,
             "Files you downloaded - real documents, not junk. Review each one before removing.",
             user_data=True),
    Category("ios_backups", Level.RISKY,
             "Device backups - possibly the only copy of a phone's data. Review each one.",
             user_data=True),
    Category("large_files", Level.RISKY,
             "Individually selected large files - real user content, not junk. Review each before removing.",
             user_data=True),
    Category("duplicates", Level.RISKY,
             "Extra copies of identical files. One copy of each is always kept - you choose which copies go.",
             user_data=True),
    Category("project_artifacts", Level.CAUTION,
             "Build artifacts and dependency folders (node_modules, venvs, target). "
             "Regenerable with one install command - but the project is broken until you run it.",
             user_data=True),
    Category("docker_junk", Level.RISKY,
             "Docker images, build cache and (only if you explicitly include them) volumes. "
             "Pruned by Docker itself - cannot be undone.",
             via_trash=False),
    Category("ios_simulators", Level.RISKY,
             "Unavailable iOS Simulator runtimes and devices. Deleted by Xcode's simctl - cannot be undone.",
             via_trash=False),
    Category("recents", Level.RISKY,
             "The list of recently opened files; clearing rewrites it in place and cannot be undone.",
             via_trash=False),
    Category("snapshots", Level.RISKY,
             "Time Machine restore points; deleting one permanently removes that restore point.",
             via_trash=False),
]

REGISTRY: dict[str, Category] = {c.key: c for c in _CATEGORIES}


def get(key: str) -> Category:
    try:
        return REGISTRY[key]
    except KeyError:
        raise UnknownCategoryError(
            f"Category '{key}' is not registered. Every cleanable category must be "
            f"declared in core/registry.py with a level and explanation."
        ) from None
