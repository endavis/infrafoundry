"""Tests for the migrate name helpers (#1337)."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrafoundry.core.exceptions import DuplicateResourceNameError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense.components._migrate_names import (
    env_provider_resources,
    reserved_names,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_env_provider_resources_filters_provider(tmp_path: Path) -> None:
    _write(
        tmp_path / "env" / "opnsense" / "unbound.yaml",
        "opnsense:\n  unbound:\n    host_overrides:\n      - name: web\n        config: {}\n",
    )
    _write(tmp_path / "env" / "proxmox" / "vm.yaml", "vm:\n  - name: guest\n    cores: 1\n")
    rows = env_provider_resources(tmp_path, "env", "opnsense")
    assert [(r.provider, r.name) for r in rows] == [("opnsense", "web")]


def test_env_provider_resources_missing_env_is_empty(tmp_path: Path) -> None:
    assert env_provider_resources(tmp_path, "nope", "opnsense") == []


def test_env_provider_resources_raises_on_existing_duplicate(tmp_path: Path) -> None:
    body = "opnsense:\n  {leaf}:\n    - name: same\n      config: {{}}\n"
    _write(
        tmp_path / "env" / "resources" / "a.yaml", body.format(leaf="unbound:\n    host_overrides")
    )
    _write(tmp_path / "env" / "resources" / "b.yaml", body.format(leaf="acmeclient:\n    accounts"))
    with pytest.raises(DuplicateResourceNameError):
        env_provider_resources(tmp_path, "env", "opnsense")


def test_reserved_names_honours_exclude_types() -> None:
    rows = [
        ResourceConfig(name="a", type="unbound.host_overrides", provider="opnsense", config={}),
        ResourceConfig(name="b", type="acmeclient.certs", provider="opnsense", config={}),
    ]
    assert reserved_names(rows, exclude_types={"unbound.host_overrides"}) == {"b"}
    assert reserved_names(rows, exclude_types=()) == {"a", "b"}
