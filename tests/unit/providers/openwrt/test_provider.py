"""Tests for the OpenWrt provider."""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.core.protocols import ValidatesOffline
from infrafoundry.core.requirements.models import CollectionRequirement
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.openwrt import OpenWrtProvider
from infrafoundry.providers.openwrt.schema import SPECS
from infrafoundry.providers.openwrt.settings import OpenWrtSettings

from .conftest import fixture_text, lan, make_env, printer, res, web

SETTINGS = OpenWrtSettings(
    address="192.0.2.2", ssh_user="admin-example", ssh_private_key_file="/keys/example"
)


def _provider(tmp_path: Path) -> OpenWrtProvider:
    return OpenWrtProvider(tmp_path, tmp_path / "generated")


def _render(provider: OpenWrtProvider, *resources: object, **kwargs: object):  # type: ignore[no-untyped-def]
    with patch("infrafoundry.providers.openwrt.load_settings", return_value=SETTINGS):
        return provider.render_run("test", list(resources), **kwargs)  # type: ignore[arg-type]


def _task_names(provider: OpenWrtProvider) -> list[str]:
    play = yaml.safe_load((provider.ansible_dir / "openwrt.yml").read_text())
    return [t["name"] for t in play[0]["tasks"][-1]["block"] if "|commit|" not in t["name"]]


def test_resource_types_and_dependencies(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    assert provider.name == "openwrt"
    assert provider.get_resource_types() == list(SPECS)
    assert provider.get_dependencies() == {name: [] for name in SPECS}


def test_terraform_prefixes_match_runner_outcome_addresses(tmp_path: Path) -> None:
    prefixes = _provider(tmp_path).get_terraform_resource_types()
    assert prefixes["dhcp.host"] == ["openwrt_dhcp_host"]
    assert prefixes["firewall.redirect"] == ["openwrt_firewall_redirect"]


def test_generate_terraform_writes_an_empty_block(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    provider.generate_terraform([])
    text = (provider.terraform_dir / "main.tf").read_text()
    assert "terraform {}" in text
    assert "backend" not in text


def test_dispatch_hook_and_ansible_directory(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    provider.generate_openwrt_ansible([])
    provider.generate_ansible([])
    assert provider.ansible_dir.is_dir()


def test_provider_declares_the_collection_it_needs(tmp_path: Path) -> None:
    assert _provider(tmp_path).ansible_collection_requirements() == (
        CollectionRequirement("community.openwrt", ">=1.11.0"),
    )


def test_implements_validates_offline(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    assert isinstance(provider, ValidatesOffline)
    report = ValidationReport()
    provider.validate_offline([lan(bogus=1)], [], make_env({"address": "192.0.2.2"}), report)
    assert any(not r.passed for r in report.results)
    provider.validate_references([lan()], make_env({"address": "192.0.2.2"}), ValidationReport())


def test_deletable_types(tmp_path: Path) -> None:
    assert _provider(tmp_path).deletable_types() == {"dhcp.host", "firewall.redirect"}


def test_render_writes_inventory_config_and_playbook(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    run = _render(provider, lan(), printer())
    assert run.playbook == "openwrt.yml"
    assert run.ansible_dir == provider.ansible_dir
    assert {p.name for p in provider.ansible_dir.iterdir()} == {
        "ansible.cfg",
        "inventory.yml",
        "openwrt.yml",
    }
    inventory = yaml.safe_load((provider.ansible_dir / "inventory.yml").read_text())
    assert inventory == {
        "all": {
            "hosts": {
                "openwrt": {
                    "ansible_host": "192.0.2.2",
                    "ansible_port": 22,
                    "ansible_user": "admin-example",
                    "ansible_ssh_private_key_file": "/keys/example",
                }
            }
        }
    }
    config = (provider.ansible_dir / "ansible.cfg").read_text()
    assert "host_key_checking = True" in config
    assert "pipelining = True" in config
    assert not (provider.ansible_dir / "playbook.yml").exists()


def test_render_rejects_invalid_resources(tmp_path: Path) -> None:
    with pytest.raises(SchemaValidationError, match="unknown field"):
        _render(_provider(tmp_path), lan(bogus=1))


def test_render_skips_other_providers_types(tmp_path: Path) -> None:
    other = res("vm", "x")
    run = _render(_provider(tmp_path), other, lan())
    assert [i.name for i in run.spec.items] == ["lan"]


def test_render_without_targets_has_no_tags(tmp_path: Path) -> None:
    assert _render(_provider(tmp_path), lan(), printer()).tags == []


def test_render_with_targets_selects_them_and_tags_the_run(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    run = _render(provider, lan(), printer(), web(), target_resources=["web", "printer"])
    assert run.tags == ["printer", "web"]
    names = _task_names(provider)
    assert "infrafoundry|dhcp.host|printer" in names
    assert "infrafoundry|firewall.redirect|web" in names
    assert "infrafoundry|network.interface|lan" not in _task_names(provider)


def test_managed_undeclared_rows_are_deleted_and_released(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    managed = {"dhcp.host": [printer()], "network.interface": [lan()]}
    run = _render(provider, web(), managed_resources=managed)
    assert "infrafoundry|absent|dhcp.host|printer" in _task_names(provider)
    assert run.spec.removal_names == {"printer"}
    assert [(r["resource_type"], r["name"]) for r in run.spec.forgotten] == [
        ("network.interface", "lan")
    ]


def test_add_only_and_targets_suppress_deletes(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    managed = {"dhcp.host": [printer()]}
    run = _render(provider, web(), managed_resources=managed, add_only=True)
    assert "infrafoundry|absent|dhcp.host|printer" not in _task_names(provider)
    assert (run.spec.removal_names, run.spec.forgotten) == (set(), [])
    run = _render(provider, web(), managed_resources=managed, target_resources=["web"])
    assert "infrafoundry|absent|dhcp.host|printer" not in _task_names(provider)
    assert run.spec.managed_names == {("dhcp.host", "printer")}


def test_destroy_deletes_declared_deletable_objects_and_forgets_the_rest(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    run = _render(provider, lan(), printer(), web(), mode="destroy")
    assert _task_names(provider) == [
        "infrafoundry|absent|dhcp.host|printer",
        "infrafoundry|absent|firewall.redirect|web",
    ]
    assert [i.name for i in run.spec.forgotten_items] == ["lan"]
    assert run.spec.mode == "destroy"
    assert "|guard|" not in "".join(_task_names(provider))


def test_inventory_and_playbook_hold_no_secret_material(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    _render(provider, lan())
    text = "".join(p.read_text() for p in provider.ansible_dir.iterdir())
    assert "password" not in text.lower()
    assert "secret" not in text.lower()


def test_parse_run_interprets_the_output_against_the_run(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    run = _render(provider, lan(), printer(), web())
    result = provider.parse_run(
        fixture_text("check_changed"), run, check=True, resolve=lambda host: host
    )
    assert result.counts == {"create": 2, "update": 0, "delete": 0}
