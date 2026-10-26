"""Check blueprint requirements against the running environment.

Python distributions are checked in the interpreter running InfraFoundry, with
``importlib.metadata``. Ansible collections are checked with ``ansible-galaxy
collection list``. Ansible's local-connection modules run under the interpreter
Ansible discovers unless the inventory pins ``ansible_python_interpreter``, so a
blueprint whose modules need these packages should pin it to
``{{ ansible_playbook_python }}`` (#1049).
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import shutil
import subprocess  # nosec B404 - runs ansible-galaxy with a fixed argument list
from collections.abc import Callable, Mapping
from typing import Any

from packaging.version import InvalidVersion, Version

from infrafoundry.core.requirements.models import (
    CollectionRequirement,
    PythonRequirement,
    RequirementKind,
    RequirementStatus,
)

VersionLookup = Callable[[str], str]
SpecFinder = Callable[[str], Any]
GalaxyRunner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def check_python(
    requirement: PythonRequirement,
    blueprints: tuple[str, ...],
    *,
    get_version: VersionLookup = importlib.metadata.version,
    find_spec: SpecFinder = importlib.util.find_spec,
) -> RequirementStatus | None:
    """Check one Python requirement in the current interpreter.

    Args:
        requirement: The requirement to check
        blueprints: Blueprints that declare it
        get_version: Returns a distribution's installed version
        find_spec: Locates an importable module

    Returns:
        The status, or ``None`` when the requirement's environment marker
        excludes this interpreter
    """
    req = requirement.requirement
    if req.marker is not None and not req.marker.evaluate():
        return None
    wanted = str(req.specifier)
    fix = f"uv pip install '{requirement.spec}'"

    try:
        installed: str | None = get_version(req.name)
    except importlib.metadata.PackageNotFoundError:
        installed = None

    def status(satisfied: bool, problem: str = "") -> RequirementStatus:
        return RequirementStatus(
            kind=RequirementKind.PYTHON,
            name=req.name,
            wanted=wanted,
            installed=installed,
            satisfied=satisfied,
            blueprints=blueprints,
            problem=problem,
            fix="" if satisfied else fix,
        )

    if installed is None:
        return status(False, "not installed")
    if not req.specifier.contains(installed, prereleases=True):
        return status(False, f"installed {installed}, needs {wanted}")
    if requirement.import_name and _module_missing(requirement.import_name, find_spec):
        return status(False, f"installed, but module '{requirement.import_name}' does not import")
    return status(True)


def _module_missing(name: str, find_spec: SpecFinder) -> bool:
    try:
        spec = find_spec(name)
    except (ImportError, ValueError):
        return True
    return spec is None


def installed_collections(
    run: GalaxyRunner | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, str] | None:
    """Return installed Ansible collections and their versions.

    Args:
        run: Runs ``ansible-galaxy``; defaults to :func:`subprocess.run`
        which: Locates the ``ansible-galaxy`` executable

    Returns:
        Collection name to version, first match on the collections path winning,
        or ``None`` when ``ansible-galaxy`` is unavailable or fails
    """
    if which("ansible-galaxy") is None:
        return None
    runner = run or _run_galaxy
    result = runner(["ansible-galaxy", "collection", "list", "--format", "json"])
    if result.returncode != 0:
        return None
    try:
        by_path: Mapping[str, Mapping[str, Mapping[str, str]]] = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    found: dict[str, str] = {}
    for collections in by_path.values():
        for name, info in collections.items():
            found.setdefault(name, str(info.get("version", "*")))
    return found


def _run_galaxy(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 - fixed argument list, no shell
        args, capture_output=True, text=True, check=False, timeout=120
    )


def check_collection(
    requirement: CollectionRequirement,
    blueprints: tuple[str, ...],
    installed: Mapping[str, str] | None,
    collections_files: tuple[str, ...],
) -> RequirementStatus:
    """Check one Ansible collection against the installed collections.

    Args:
        requirement: The collection to check
        blueprints: Blueprints that declare it
        installed: Result of :func:`installed_collections`
        collections_files: Requirements files that declare it, for the fix command

    Returns:
        The status
    """
    wanted = requirement.version or ""
    fix = (
        " && ".join(f"ansible-galaxy collection install -r {path}" for path in collections_files)
        or f"ansible-galaxy collection install '{requirement.name}{wanted}'"
    )
    version = None if installed is None else installed.get(requirement.name)

    def status(satisfied: bool, problem: str = "") -> RequirementStatus:
        return RequirementStatus(
            kind=RequirementKind.ANSIBLE_COLLECTION,
            name=requirement.name,
            wanted=wanted,
            installed=version,
            satisfied=satisfied,
            blueprints=blueprints,
            problem=problem,
            fix="" if satisfied else fix,
        )

    if installed is None:
        return status(False, "ansible-galaxy is not available to list installed collections")
    if version is None:
        return status(False, "not installed")
    if requirement.version is None:
        return status(True)
    try:
        ok = requirement.specifier.contains(Version(version), prereleases=True)
    except InvalidVersion:
        return status(False, f"installed version '{version}' cannot be compared with {wanted}")
    return status(True) if ok else status(False, f"installed {version}, needs {wanted}")
