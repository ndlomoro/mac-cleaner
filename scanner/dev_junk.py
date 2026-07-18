"""Dev-junk scanner - project build artifacts, Docker, iOS Simulators.

Staleness (see /CONTEXT.md 'Stale') is measured on the project's sources,
never on the artifact itself.
"""
import os
from pathlib import Path

from utils.helpers import HOME, file_age_days, get_dir_size

PROJECT_ROOTS = [
    HOME / "Documents",
    HOME / "Develop",
    HOME / "Developer",
    HOME / "Projects",
]
MAX_DEPTH = 4

# kind -> (artifact dir name, sibling marker that confirms a project)
_ARTIFACT_MARKERS = {
    "node_modules": ("node_modules", "package.json"),
    "rust_target": ("target", "Cargo.toml"),
}
_SKIP_DIRS = {"node_modules", "target", ".git", "Library", ".Trash"}
_PRUNE_DIRS = _SKIP_DIRS | {"venv", ".venv"}

# standalone cache roots reported as single entries
_CACHE_ROOTS = [
    ("gradle_cache", HOME / ".gradle" / "caches"),
    ("maven_repo", HOME / ".m2" / "repository"),
]


def _looks_like_venv(dirpath: str, name: str) -> bool:
    try:
        return (Path(dirpath) / name / "pyvenv.cfg").exists()
    except (OSError, PermissionError):
        return False


def _project_source_age(project: Path) -> int:
    """Days since the project's newest source mtime. Prunes all artifact dirs
    (node_modules/target/venvs/.git) topdown - never enters them."""
    newest = None
    for dirpath, dirnames, filenames in os.walk(project, topdown=True, onerror=lambda e: None):
        dirnames[:] = [d for d in dirnames
                       if d not in _PRUNE_DIRS
                       and not d.startswith(".")
                       and not _looks_like_venv(dirpath, d)]
        for fname in filenames:
            try:
                age = file_age_days(Path(dirpath) / fname)
            except (OSError, PermissionError):
                continue
            if newest is None or age < newest:
                newest = age
    return int(newest) if newest is not None else int(file_age_days(project))


def _venv_dirs(candidate: Path) -> list[Path]:
    out = []
    for name in (".venv", "venv"):
        v = candidate / name
        if (v / "pyvenv.cfg").exists():
            out.append(v)
    return out


def find_project_artifacts() -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()

    def _walk(directory: Path, depth: int) -> None:
        if depth > MAX_DEPTH:
            return
        try:
            children = list(directory.iterdir())
        except (OSError, PermissionError):
            return
        names = {c.name for c in children}
        found_here = False

        for kind, (artifact_name, marker) in _ARTIFACT_MARKERS.items():
            if artifact_name in names and marker in names:
                artifact = directory / artifact_name
                if str(artifact) in seen or not artifact.is_dir():
                    continue
                seen.add(str(artifact))
                results.append({
                    "path": str(artifact),
                    "size": get_dir_size(artifact),
                    "age_days": _project_source_age(directory),
                    "kind": kind,
                    "project": directory.name,
                })
                found_here = True

        for venv in _venv_dirs(directory):
            if str(venv) in seen:
                continue
            seen.add(str(venv))
            results.append({
                "path": str(venv),
                "size": get_dir_size(venv),
                "age_days": _project_source_age(directory),
                "kind": "venv",
                "project": directory.name,
            })
            found_here = True

        if found_here:
            return  # prune: never descend past a project hit
        for child in children:
            if child.is_dir() and not child.is_symlink() \
                    and child.name not in _SKIP_DIRS and not child.name.startswith("."):
                _walk(child, depth + 1)

    for root in PROJECT_ROOTS:
        if root.exists():
            _walk(root, 0)

    for kind, cache_root in _CACHE_ROOTS:
        if cache_root.exists():
            results.append({
                "path": str(cache_root),
                "size": get_dir_size(cache_root),
                "age_days": int(file_age_days(cache_root)),
                "kind": kind,
                "project": kind.replace("_", " "),
            })

    results.sort(key=lambda r: r["age_days"], reverse=True)
    return results
