"""Parsing and validation of a blueprint's ``requirements:`` block (#1046)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.exceptions import InvalidConfigurationError
from infrafoundry.core.requirements.models import (
    BlueprintRequirements,
    CollectionRequirement,
    PythonRequirement,
)


def _parse(raw: Any, blueprint_dir: Path) -> BlueprintRequirements:
    return BlueprintRequirements.parse(raw, blueprint_dir, "demo")


def _collections_file(blueprint_dir: Path, body: str) -> None:
    (blueprint_dir / "requirements.yml").write_text(body, encoding="utf-8")


def test_absent_block_means_no_requirements(tmp_path: Path) -> None:
    assert _parse(None, tmp_path) == BlueprintRequirements()


def test_python_entries_accept_strings_and_mappings(tmp_path: Path) -> None:
    parsed = _parse(
        {"python": ["requests>=2", {"spec": "netapp-lib>=2021.6.25", "import": "netapp_lib"}]},
        tmp_path,
    )

    assert parsed.python == (
        PythonRequirement(spec="requests>=2"),
        PythonRequirement(spec="netapp-lib>=2021.6.25", import_name="netapp_lib"),
    )
    assert parsed.collections == ()


def test_collections_file_is_read_relative_to_the_blueprint(tmp_path: Path) -> None:
    _collections_file(
        tmp_path,
        "collections:\n"
        "  - name: netapp.ontap\n    version: '>=22.0.0'\n"
        "  - community.general\n"
        "  - name: ansible.posix\n    version: '*'\n"
        "  - name: exact.pin\n    version: 1.2.3\n",
    )

    parsed = _parse({"ansible_collections": "requirements.yml"}, tmp_path)

    assert parsed.collections_file == (tmp_path / "requirements.yml").resolve()
    assert parsed.collections == (
        CollectionRequirement(name="netapp.ontap", version=">=22.0.0"),
        CollectionRequirement(name="community.general"),
        CollectionRequirement(name="ansible.posix"),
        CollectionRequirement(name="exact.pin", version="==1.2.3"),
    )


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (["netapp-lib"], "must be a mapping"),
        ({"pip": []}, "unknown key(s) pip"),
        ({"python": "netapp-lib"}, "must be a list"),
        ({"python": ["not a valid spec!!"]}, "invalid requirement"),
        ({"python": [{"spec": ""}]}, "'spec' must be a non-empty"),
        ({"python": [{"spec": "x", "module": "y"}]}, "unknown key(s) module"),
        ({"python": [{"spec": "x", "import": ""}]}, "'import' must be a non-empty"),
        ({"python": [42]}, "must be a string or a mapping"),
        ({"ansible_collections": "missing.yml"}, "file not found"),
        ({"ansible_collections": "../outside.yml"}, "points outside the blueprint"),
    ],
)
def test_invalid_blocks_fail_with_a_clear_error(tmp_path: Path, raw: Any, message: str) -> None:
    with pytest.raises(InvalidConfigurationError) as excinfo:
        _parse(raw, tmp_path)

    assert message in str(excinfo.value)
    assert "blueprint 'demo'" in str(excinfo.value)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("collections: [", "invalid YAML"),
        ("- netapp.ontap\n", "must be a mapping"),
        ("collections:\n  - version: 1.0.0\n", "must be a name or have 'name'"),
        ("collections:\n  - name: a.b\n    version: '>>1'\n", "invalid version"),
    ],
)
def test_invalid_collections_files_fail(tmp_path: Path, body: str, message: str) -> None:
    _collections_file(tmp_path, body)

    with pytest.raises(InvalidConfigurationError, match=r"requirements\.yml") as excinfo:
        _parse({"ansible_collections": "requirements.yml"}, tmp_path)

    assert message in str(excinfo.value)
