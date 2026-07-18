"""Dev-junk scanner - project build artifacts, Docker, iOS Simulators.

Staleness (see /CONTEXT.md 'Stale') is measured on the project's sources,
never on the artifact itself.
"""
import json
import os
import shutil as _shutil
from pathlib import Path

from utils.helpers import HOME, file_age_days, get_dir_size, run_command

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


def _looks_like_venv(candidate: Path) -> bool:
    """True if `candidate` is a directory containing pyvenv.cfg. Guarded: a
    permission-denied candidate must never crash the scan."""
    try:
        return (candidate / "pyvenv.cfg").exists()
    except (OSError, PermissionError):
        return False


def _project_source_age(project: Path) -> int:
    """Days since the project's newest source mtime. Prunes all artifact dirs
    (node_modules/target/venvs/.git) topdown - never enters them."""
    newest = None
    for dirpath, dirnames, filenames in os.walk(project, topdown=True):
        dirnames[:] = [d for d in dirnames
                       if d not in _PRUNE_DIRS
                       and not d.startswith(".")
                       and not _looks_like_venv(Path(dirpath) / d)]
        for fname in filenames:
            age = file_age_days(Path(dirpath) / fname)
            if newest is None or age < newest:
                newest = age
    return int(newest) if newest is not None else int(file_age_days(project))


def _venv_dirs(candidate: Path) -> list[Path]:
    out = []
    for name in (".venv", "venv"):
        v = candidate / name
        if _looks_like_venv(v):
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


def _which(name: str) -> str | None:
    return _shutil.which(name)


_UNITS = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}


def _parse_docker_size(text) -> int:
    """Parse a docker size string, e.g. '8GB' or '1.5GB (50%)'. Docker's own
    convention uses decimal units (GB=1000**3), not binary (GiB). Tolerates
    non-str input (e.g. a null Reclaimable field) by returning 0."""
    if not isinstance(text, str):
        return 0
    text = text.strip().split()[0] if text.strip() else text.strip()
    for unit in ("TB", "GB", "MB", "KB", "B"):
        if text.upper().endswith(unit):
            return int(float(text[: -len(unit)]) * _UNITS[unit])
    return 0


def find_docker_junk() -> dict | None:
    """Reclaimable Docker sizes via `docker system df`. None when docker is absent."""
    if not _which("docker"):
        return None
    stdout, _, rc = run_command(["docker", "system", "df", "--format", "{{json .}}"])
    if rc != 0:
        return None
    sizes = {"images_bytes": 0, "volumes_bytes": 0, "build_cache_bytes": 0}
    key_map = {"Images": "images_bytes", "Local Volumes": "volumes_bytes",
               "Build Cache": "build_cache_bytes"}
    for line in stdout.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        key = key_map.get(row.get("Type", ""))
        if key:
            sizes[key] = _parse_docker_size(row.get("Reclaimable", "0B"))
    return sizes


def find_simulators() -> list[dict]:
    """Unavailable simulator devices. [] when xcrun is absent."""
    if not _which("xcrun"):
        return []
    stdout, _, rc = run_command(["xcrun", "simctl", "list", "devices", "-j"])
    if rc != 0:
        return []
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    devices_by_runtime = data.get("devices")
    if not isinstance(devices_by_runtime, dict):
        return []
    sims = []
    for runtime, devices in devices_by_runtime.items():
        for d in devices:
            if not isinstance(d, dict):
                continue
            if not d.get("isAvailable", True):
                sims.append({"name": d.get("name", "?"), "kind": "device",
                             "size": 0, "udid": d.get("udid", "")})
    return sims
