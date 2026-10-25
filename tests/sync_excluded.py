"""Recognize paths InfraFoundry deliberately does not adopt from pyproject-template.

Template-owned files (the 9xxx ADRs, the shared skills) link to upstream files
that `.config/pyproject_template/sync-exclude.toml` keeps out of this repository:
the skeleton package, the template's own docs. Those links are correct upstream
and are left byte-identical here, so a template sync does not re-break them.
The link and documented-path tests use this to skip such targets instead of
reporting them as broken (#1057). A link to anything else that is missing still
fails.
"""

from __future__ import annotations

from fnmatch import fnmatch
from functools import cache
from pathlib import Path

from tools.pyproject_template.check_template_updates import load_sync_excludes

REPO_ROOT = Path(__file__).resolve().parents[1]


@cache
def _patterns() -> tuple[str, ...]:
    return tuple(load_sync_excludes(REPO_ROOT))


def is_sync_excluded(path: Path | str) -> bool:
    """Return whether *path* matches a sync-exclude pattern.

    Args:
        path: An absolute path inside the repository, or a repo-relative one

    Returns:
        True when the path is one the template ships and this repository excludes
    """
    candidate = Path(path)
    if candidate.is_absolute():
        if REPO_ROOT not in candidate.parents:
            return False
        candidate = candidate.relative_to(REPO_ROOT)
    rel = candidate.as_posix()
    return any(fnmatch(rel, pattern) for pattern in _patterns())
