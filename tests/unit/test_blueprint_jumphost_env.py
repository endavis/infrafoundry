"""Blueprint scripts may only read framework variables available on a jumphost (#1164)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from infrafoundry.core.events.handlers.script import JUMPHOST_FORWARDED_ENV

REPO_ROOT = Path(__file__).resolve().parents[2]
BLUEPRINTS = REPO_ROOT / "blueprints"

_TOKEN_RE = re.compile(r"INFRAFOUNDRY_[A-Z][A-Z_]*")
_SUFFIXES = {".sh", ".py"}


def _has_guard(text: str, token: str) -> bool:
    """True if an `if` tests both INFRAFOUNDRY_ON_JUMPHOST and ``token``."""
    pattern = rf"^\s*if .*INFRAFOUNDRY_ON_JUMPHOST.*{token}"
    return re.search(pattern, text, re.MULTILINE) is not None


# (script relative to blueprints/, variable) pairs not forwarded to a jumphost but
# guarded by an INFRAFOUNDRY_ON_JUMPHOST check in the script.
JUMPHOST_GUARDED: set[tuple[str, str]] = {
    ("k3s-cluster/scripts/oci/k3s-post-terraform.sh", "INFRAFOUNDRY_CONFIG_DIR"),
}


def _scripts() -> list[Path]:
    return sorted(
        p for p in BLUEPRINTS.glob("*/scripts/**/*") if p.is_file() and p.suffix in _SUFFIXES
    )


def _tokens(path: Path) -> set[str]:
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue
        for token in _TOKEN_RE.findall(line):
            if not token.startswith("INFRAFOUNDRY_VAR_") and token != "INFRAFOUNDRY_VAR_":
                found.add(token)
    return found


def _rel(path: Path) -> str:
    return path.relative_to(BLUEPRINTS).as_posix()


def test_scan_covers_every_blueprint_with_scripts() -> None:
    """The glob finds scripts in each blueprint that has a scripts/ directory."""
    scanned = {_rel(p).split("/", 1)[0] for p in _scripts()}
    expected = {d.parent.name for d in BLUEPRINTS.glob("*/scripts") if d.is_dir()}
    assert expected
    assert expected <= scanned


@pytest.mark.parametrize("script", _scripts(), ids=_rel)
def test_script_reads_only_jumphost_available_env(script: Path) -> None:
    """Every INFRAFOUNDRY_* a script reads is forwarded to the jumphost or guarded."""
    rel = _rel(script)
    unavailable = []
    for token in sorted(_tokens(script)):
        if token in JUMPHOST_FORWARDED_ENV:
            continue
        if (rel, token) in JUMPHOST_GUARDED:
            assert _has_guard(script.read_text(encoding="utf-8"), token), (
                f"{rel} is allowlisted for {token} but has no INFRAFOUNDRY_ON_JUMPHOST guard for it"
            )
            continue
        unavailable.append(token)
    assert unavailable == [], f"{rel} reads variables not available on a jumphost: {unavailable}"
