"""Scoping, de-duplication and enforcement of blueprint requirements (#1046)."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any

import pytest
import yaml

from infrafoundry.core.config import ConfigManager
from infrafoundry.core.exceptions import InvalidConfigurationError, MissingRequirementsError
from infrafoundry.core.requirements.manager import RequirementsManager
from infrafoundry.core.requirements.models import RequirementKind


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.fixture
def config_manager(tmp_path: Path) -> ConfigManager:
    """An env ``dev`` whose packages use blueprints ``bp-a`` and ``bp-b``.

    - ``proxmox/vm-a`` uses ``bp-a`` (needs ``alpha>=1`` and ``netapp.ontap``)
    - ``proxmox/vm-b`` uses ``bp-b`` (needs ``alpha>=1`` and ``beta``)
    - ``proxmox/plain`` uses no blueprint
    - ``k8s-pkg`` is an env-root package for ``kubernetes`` using ``bp-b``
    """
    envs = tmp_path / "config" / "envs"
    blueprints = tmp_path / "config" / "blueprints"
    _write(
        envs / "dev" / "proxmox" / "vm-a" / "infrafoundry.yml",
        {"name": "vm-a", "blueprint": "bp-a"},
    )
    _write(
        envs / "dev" / "proxmox" / "vm-b" / "infrafoundry.yml",
        {"name": "vm-b", "blueprint": "bp-b"},
    )
    _write(envs / "dev" / "proxmox" / "plain" / "infrafoundry.yml", {"name": "plain"})
    _write(
        envs / "dev" / "k8s-pkg" / "infrafoundry.yml",
        {"name": "k8s-pkg", "provider": "kubernetes", "blueprint": "bp-b"},
    )
    _write(
        blueprints / "bp-a" / "blueprint.yaml",
        {
            "name": "bp-a",
            "requirements": {
                "python": ["alpha>=1"],
                "ansible_collections": "requirements.yml",
            },
        },
    )
    _write(
        blueprints / "bp-a" / "requirements.yml",
        {"collections": [{"name": "netapp.ontap", "version": ">=22.0.0"}]},
    )
    _write(
        blueprints / "bp-b" / "blueprint.yaml",
        {"name": "bp-b", "requirements": {"python": ["alpha>=1", "beta"]}},
    )
    manager = ConfigManager(base_dir=envs)
    manager.blueprint_resolver.blueprints_dir = blueprints
    return manager


def _versions(**installed: str) -> Any:
    def get_version(name: str) -> str:
        if name in installed:
            return installed[name]
        raise importlib.metadata.PackageNotFoundError(name)

    return get_version


def _manager(
    config_manager: ConfigManager,
    installed: dict[str, str],
    collections: dict[str, str] | None = None,
) -> tuple[RequirementsManager, list[str]]:
    calls: list[str] = []

    def lookup() -> dict[str, str] | None:
        calls.append("galaxy")
        return collections

    manager = RequirementsManager(
        config_manager,
        get_version=_versions(**installed),
        find_spec=lambda _: object(),
        collections_lookup=lookup,
    )
    return manager, calls


def test_list_package_manifests_covers_provider_and_env_root_packages(
    config_manager: ConfigManager,
) -> None:
    found = {
        (provider, m.name, m.blueprint)
        for provider, m in config_manager.list_package_manifests("dev")
    }

    assert found == {
        ("proxmox", "vm-a", "bp-a"),
        ("proxmox", "vm-b", "bp-b"),
        ("proxmox", "plain", None),
        ("kubernetes", "k8s-pkg", "bp-b"),
    }


@pytest.mark.parametrize(
    ("package_filter", "provider_filter", "expected"),
    [
        (None, None, ["bp-a", "bp-b"]),
        ("vm-a", None, ["bp-a"]),
        ("plain", None, []),
        (None, ["kubernetes"], ["bp-b"]),
        (None, ["opnsense"], []),
    ],
)
def test_blueprints_in_scope_follow_the_package_and_provider_filters(
    config_manager: ConfigManager,
    package_filter: str | None,
    provider_filter: list[str] | None,
    expected: list[str],
) -> None:
    manager, _ = _manager(config_manager, {})

    assert manager.blueprints_in_scope("dev", package_filter, provider_filter) == expected


def test_requirements_are_deduplicated_across_blueprints(config_manager: ConfigManager) -> None:
    report = _manager(config_manager, {"alpha": "1.0", "beta": "2.0"}, {"netapp.ontap": "22.1.0"})[
        0
    ].check("dev")

    by_name = {(s.kind, s.name): s for s in report.statuses}
    assert len(report.statuses) == 3
    assert by_name[(RequirementKind.PYTHON, "alpha")].blueprints == ("bp-a", "bp-b")
    assert by_name[(RequirementKind.PYTHON, "beta")].blueprints == ("bp-b",)
    assert by_name[(RequirementKind.ANSIBLE_COLLECTION, "netapp.ontap")].satisfied
    assert report.unmet == ()


def test_only_requirements_in_scope_are_checked(config_manager: ConfigManager) -> None:
    manager, galaxy_calls = _manager(config_manager, {"alpha": "1.0", "beta": "2.0"})

    report = manager.check("dev", provider_filter=["kubernetes"])

    assert {s.name for s in report.statuses} == {"alpha", "beta"}
    assert galaxy_calls == []


def test_ensure_raises_naming_the_package_blueprint_and_fix(config_manager: ConfigManager) -> None:
    manager, _ = _manager(config_manager, {"alpha": "0.5"}, {})

    with pytest.raises(MissingRequirementsError) as excinfo:
        manager.ensure("dev")

    message = str(excinfo.value)
    assert "environment 'dev'" in message
    assert "python alpha>=1: installed 0.5, needs >=1 (needed by blueprint bp-a, bp-b)" in message
    assert "run: uv pip install 'alpha>=1'" in message
    assert "python beta: not installed (needed by blueprint bp-b)" in message
    assert "ansible_collection netapp.ontap>=22.0.0: not installed" in message
    assert "run: ansible-galaxy collection install -r " in message
    assert excinfo.value.context["unmet"] == ["alpha", "beta", "netapp.ontap"]


def test_ensure_returns_the_report_when_everything_is_met(config_manager: ConfigManager) -> None:
    manager, _ = _manager(
        config_manager, {"alpha": "1.0", "beta": "2.0"}, {"netapp.ontap": "22.1.0"}
    )

    report = manager.ensure("dev")

    assert report.format_unmet() == ""
    assert len(report.statuses) == 3


def test_an_invalid_requirements_block_surfaces_as_configuration_error(
    config_manager: ConfigManager,
) -> None:
    bp = config_manager.blueprint_resolver.blueprints_dir / "bp-b" / "blueprint.yaml"
    _write(bp, {"name": "bp-b", "requirements": {"python": ["!!bad"]}})

    with pytest.raises(InvalidConfigurationError, match="blueprint 'bp-b'"):
        _manager(config_manager, {})[0].check("dev")
