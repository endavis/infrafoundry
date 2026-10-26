"""Checks of Python and Ansible collection requirements (#1046)."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
from typing import Any

import pytest

from infrafoundry.core.requirements.checker import (
    check_collection,
    check_python,
    installed_collections,
)
from infrafoundry.core.requirements.models import (
    CollectionRequirement,
    PythonRequirement,
    RequirementKind,
)

BLUEPRINTS = ("ontap-cluster",)


def _versions(**installed: str) -> Any:
    def get_version(name: str) -> str:
        if name in installed:
            return installed[name]
        raise importlib.metadata.PackageNotFoundError(name)

    return get_version


def _finds(*modules: str) -> Any:
    return lambda name: object() if name in modules else None


def test_python_requirement_met() -> None:
    status = check_python(
        PythonRequirement("netapp-lib>=2021.6.25", import_name="netapp_lib"),
        BLUEPRINTS,
        get_version=_versions(**{"netapp-lib": "2021.6.25"}),
        find_spec=_finds("netapp_lib"),
    )

    assert status is not None
    assert status.satisfied
    assert status.kind is RequirementKind.PYTHON
    assert (status.installed, status.wanted, status.fix) == ("2021.6.25", ">=2021.6.25", "")


def test_python_requirement_missing_names_the_fix() -> None:
    status = check_python(
        PythonRequirement("netapp-lib>=2021.6.25"), BLUEPRINTS, get_version=_versions()
    )

    assert status is not None
    assert not status.satisfied
    assert status.installed is None
    assert status.problem == "not installed"
    assert status.fix == "uv pip install 'netapp-lib>=2021.6.25'"
    assert status.blueprints == BLUEPRINTS


def test_python_requirement_out_of_range() -> None:
    status = check_python(
        PythonRequirement("netapp-lib>=2021.6.25"),
        BLUEPRINTS,
        get_version=_versions(**{"netapp-lib": "2020.1.1"}),
    )

    assert status is not None
    assert not status.satisfied
    assert status.problem == "installed 2020.1.1, needs >=2021.6.25"


def test_python_requirement_whose_module_does_not_import() -> None:
    status = check_python(
        PythonRequirement("netapp-lib", import_name="netapp_lib"),
        BLUEPRINTS,
        get_version=_versions(**{"netapp-lib": "2021.6.25"}),
        find_spec=_finds(),
    )

    assert status is not None
    assert not status.satisfied
    assert "module 'netapp_lib' does not import" in status.problem


def test_python_requirement_whose_import_check_raises_is_unmet() -> None:
    def broken(name: str) -> Any:
        raise ModuleNotFoundError(name)

    status = check_python(
        PythonRequirement("pkg", import_name="pkg.sub"),
        BLUEPRINTS,
        get_version=_versions(pkg="1.0"),
        find_spec=broken,
    )

    assert status is not None
    assert not status.satisfied


def test_python_requirement_excluded_by_its_marker_is_skipped() -> None:
    status = check_python(
        PythonRequirement('pywin32; sys_platform == "never"'), BLUEPRINTS, get_version=_versions()
    )

    assert status is None


def _galaxy(stdout: str, returncode: int = 0) -> Any:
    def run(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert args == ["ansible-galaxy", "collection", "list", "--format", "json"]
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")

    return run


def test_installed_collections_prefers_the_first_path() -> None:
    listing = {
        "/first": {"netapp.ontap": {"version": "22.1.0"}},
        "/second": {"netapp.ontap": {"version": "21.0.0"}, "ansible.posix": {"version": "*"}},
    }

    found = installed_collections(
        run=_galaxy(json.dumps(listing)), which=lambda _: "/usr/bin/ansible-galaxy"
    )

    assert found == {"netapp.ontap": "22.1.0", "ansible.posix": "*"}


@pytest.mark.parametrize(
    ("which", "stdout", "returncode"),
    [(None, "{}", 0), ("/usr/bin/ansible-galaxy", "", 1), ("/usr/bin/ansible-galaxy", "{", 0)],
)
def test_installed_collections_is_none_when_galaxy_cannot_answer(
    which: str | None, stdout: str, returncode: int
) -> None:
    assert installed_collections(run=_galaxy(stdout, returncode), which=lambda _: which) is None


ONTAP = CollectionRequirement("netapp.ontap", ">=22.0.0")
FILES = ("/bp/requirements.yml",)


def test_collection_met() -> None:
    status = check_collection(ONTAP, BLUEPRINTS, {"netapp.ontap": "22.1.0"}, FILES)

    assert status.satisfied
    assert status.kind is RequirementKind.ANSIBLE_COLLECTION


def test_collection_missing_points_at_its_requirements_file() -> None:
    status = check_collection(ONTAP, BLUEPRINTS, {}, FILES)

    assert not status.satisfied
    assert status.problem == "not installed"
    assert status.fix == "ansible-galaxy collection install --upgrade -r /bp/requirements.yml"
    assert status.install_args == FILES


def test_collection_out_of_range() -> None:
    status = check_collection(ONTAP, BLUEPRINTS, {"netapp.ontap": "21.9.0"}, FILES)

    assert not status.satisfied
    assert status.problem == "installed 21.9.0, needs >=22.0.0"
    # ansible-galaxy leaves an installed collection alone unless told to upgrade it.
    assert "--upgrade" in status.fix


def test_collection_without_a_version_accepts_any() -> None:
    status = check_collection(
        CollectionRequirement("ansible.posix"), BLUEPRINTS, {"ansible.posix": "*"}, ()
    )

    assert status.satisfied


def test_collection_with_an_uncomparable_version_is_unmet() -> None:
    status = check_collection(ONTAP, BLUEPRINTS, {"netapp.ontap": "*"}, ())

    assert not status.satisfied
    assert "cannot be compared" in status.problem
    assert status.fix == "ansible-galaxy collection install --upgrade 'netapp.ontap>=22.0.0'"
    assert status.install_args == ("netapp.ontap>=22.0.0",)


def test_collection_without_galaxy_is_unmet() -> None:
    status = check_collection(ONTAP, BLUEPRINTS, None, FILES)

    assert not status.satisfied
    assert "ansible-galaxy is not available" in status.problem
