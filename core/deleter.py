"""safe_delete() - the only function in this codebase allowed to destroy file data."""
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from core.dedup import KeepOneViolation, find_keep_one_violations
from core.registry import get as get_category
from core.safety import is_protected, running_apps
from core.trash import NotInTrashError, TrashError, delete_from_trash, trash_item
from utils.logger import log_cleaning_action


class Outcome(str, Enum):
    TRASHED = "trashed"
    SKIPPED = "skipped"
    FAILED = "failed"


class UserSelectionRequired(Exception):
    """A user_data category was passed without user_selected=True."""


@dataclass
class PathResult:
    path: str
    outcome: Outcome
    size: int = 0
    reason: str = ""       # skip reason or failure message
    trash_path: str = ""   # set for real (non-dry-run) trashed items


@dataclass
class DeleteReport:
    category: str
    dry_run: bool
    results: list[PathResult] = field(default_factory=list)

    def _with(self, outcome: Outcome) -> list[PathResult]:
        return [r for r in self.results if r.outcome is outcome]

    @property
    def trashed(self) -> list[PathResult]:
        return self._with(Outcome.TRASHED)

    @property
    def skipped(self) -> list[PathResult]:
        return self._with(Outcome.SKIPPED)

    @property
    def failed(self) -> list[PathResult]:
        return self._with(Outcome.FAILED)

    @property
    def trashed_bytes(self) -> int:
        return sum(r.size for r in self.trashed)


def safe_delete(items: list[dict], category: str,
                dry_run: bool = False, user_selected: bool = False) -> DeleteReport:
    """Move items to the Trash after safety checks.

    items: dicts with "path" (str) and "size" (int, scanner's estimate).
    Raises UnknownCategoryError for unregistered categories and
    UserSelectionRequired when a user_data category lacks the tripwire flag.
    """
    cat = get_category(category)
    if cat.user_data and not user_selected:
        raise UserSelectionRequired(
            f"'{category}' contains user data; items must be individually selected "
            f"and passed with user_selected=True."
        )

    running = running_apps()
    allow_user_content = cat.user_data and user_selected
    report = DeleteReport(category=category, dry_run=dry_run)

    for item in items:
        try:
            path_str = item["path"]
            size = int(item.get("size", 0))
            path = Path(path_str)
        except (KeyError, TypeError, ValueError) as e:
            report.results.append(
                PathResult(str(item), Outcome.FAILED, 0, f"malformed item: {e}"))
            continue

        protected, reason = is_protected(path, running, allow_user_content)
        if protected:
            report.results.append(PathResult(path_str, Outcome.SKIPPED, size, reason))
            continue

        if dry_run:
            log_cleaning_action("Would Trash", path_str, dry_run=True)
            report.results.append(PathResult(path_str, Outcome.TRASHED, size))
            continue

        if not path.exists() and not path.is_symlink():
            report.results.append(
                PathResult(path_str, Outcome.SKIPPED, size, "no longer exists"))
            continue

        try:
            trash_path = trash_item(path)
        except Exception as e:
            log_cleaning_action("Failed to Trash", f"{path_str} ({e})")
            report.results.append(PathResult(path_str, Outcome.FAILED, size, str(e)))
            continue

        report.results.append(
            PathResult(path_str, Outcome.TRASHED, size, trash_path=str(trash_path)))
        log_cleaning_action("Trashed", path_str)

    return report


def trash_selection(
    submission: dict[str, list[dict]],
    groups: Iterable[frozenset[str]],
    dry_run: bool = False,
) -> list[DeleteReport]:
    """Trash a whole Space Finder selection, upholding the Keep-One Invariant.

    `submission` maps category -> item dicts (path + size) - exactly the shape
    the Space Finder builds from live checkbox state. `groups` is the full
    membership of every known Duplicate Group.

    The invariant is enforced HERE, behind the deletion interface, rather than
    in the UI: the union of every path across the whole submission is checked
    before anything is trashed, so a group whose copies are picked from
    different tabs is still caught. If any group would be emptied this raises
    KeepOneViolation and nothing is touched - validate-all-then-delete, so a
    rejected batch never half-runs. On success each category is dispatched
    through safe_delete with user_selected=True (every Space Finder category is
    Reclaimable User Data) and the reports are returned in submission order.
    """
    picked_paths = {
        row["path"]
        for rows in submission.values()
        for row in rows
        if isinstance(row.get("path"), str)
    }
    violations = find_keep_one_violations(picked_paths, groups)
    if violations:
        raise KeepOneViolation(violations)

    return [
        safe_delete(rows, category, dry_run=dry_run, user_selected=True)
        for category, rows in submission.items()
        if rows
    ]


@dataclass
class ReclaimReport:
    deleted: int = 0
    failed: int = 0
    freed_bytes: int = 0


def reclaim(reports: list["DeleteReport"]) -> ReclaimReport:
    """Permanently delete ONLY the items these reports moved to the Trash.

    This is the app's irreversible 'empty now' step (typed confirmation happens
    in the UI before calling this). Items already gone are silently fine.
    """
    result = ReclaimReport()
    for report in reports:
        if report.dry_run:
            continue
        for r in report.trashed:
            if not r.trash_path:
                continue
            trash_path = Path(r.trash_path)
            if not trash_path.exists() and not trash_path.is_symlink():
                continue
            try:
                delete_from_trash(trash_path)
                result.deleted += 1
                result.freed_bytes += r.size
                log_cleaning_action("Reclaimed", r.path)
            except (NotInTrashError, OSError) as e:
                log_cleaning_action("Failed to Reclaim", f"{r.path} ({e})")
                result.failed += 1
    return result
