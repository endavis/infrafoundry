"""Tests for HostProvider."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.providers.host import HostProvider

from .conftest import AUTH_REF, SECRET_VALUE, host, make_env, tailscale_block


def test_types_terraform_map_and_dependencies(provider: HostProvider) -> None:
    assert provider.get_resource_types() == ["host"]
    assert provider.get_terraform_resource_types() == {"host": ["host"]}
    assert provider.get_dependencies() == {"host": []}
    assert provider.validate_config({"name": "x"})
    assert not provider.validate_config({})


def test_generate_terraform_writes_only_empty_terraform_block(provider: HostProvider) -> None:
    provider.generate_terraform([host()])
    files = sorted(p.name for p in provider.terraform_dir.iterdir())
    assert files == ["main.tf"]
    content = (provider.terraform_dir / "main.tf").read_text()
    assert "terraform {}" in content
    assert "resource" not in content


def test_generate_ansible_only_creates_directories(provider: HostProvider) -> None:
    provider.generate_ansible([host()])
    assert provider.ansible_dir.is_dir()
    assert list(provider.ansible_dir.iterdir()) == []


def _inventory(provider: HostProvider) -> dict[str, Any]:
    loaded = yaml.safe_load((provider.ansible_dir / "inventory.yml").read_text())
    assert isinstance(loaded, dict)
    return loaded


def test_inventory_addresses_groups_and_defaults(provider: HostProvider) -> None:
    provider.generate_host(
        [
            host("v4", address="192.0.2.10", groups=["web"], ssh_user="admin", ssh_port=2222),
            host("v6", address="2001:db8::10", groups=["web", "db"]),
            host("named", address="vps-01.example.com", ssh_private_key_file="keys/id"),
        ]
    )
    inv = _inventory(provider)["all"]
    assert inv["hosts"]["v4"] == {
        "ansible_host": "192.0.2.10",
        "ansible_port": 2222,
        "ansible_user": "admin",
    }
    assert inv["hosts"]["v6"]["ansible_host"] == "2001:db8::10"
    assert inv["hosts"]["v6"]["ansible_port"] == 22
    assert "ansible_user" not in inv["hosts"]["v6"]
    assert inv["hosts"]["named"]["ansible_ssh_private_key_file"] == "keys/id"
    assert set(inv["children"]) == {"web", "db"}
    assert set(inv["children"]["web"]["hosts"]) == {"v4", "v6"}


def test_ansible_cfg_has_roles_path(provider: HostProvider, repo: Path) -> None:
    provider.generate_host([host()])
    cfg = (provider.ansible_dir / "ansible.cfg").read_text()
    assert f"roles_path = {(repo / 'roles').resolve()}" in cfg


def test_tailscale_playbook_only_with_a_tailscale_block(provider: HostProvider) -> None:
    provider.generate_host([host()])
    assert not (provider.ansible_dir / "tailscale.yml").exists()
    assert not (provider.ansible_dir / "playbook.yml").exists()

    provider.generate_host([host(tailscale=tailscale_block())])
    playbook = (provider.ansible_dir / "tailscale.yml").read_text()
    assert "--auth-key=file:" in playbook
    assert yaml.safe_load(playbook)[0]["hosts"] == "all"

    provider.generate_host([host()])
    assert not (provider.ansible_dir / "tailscale.yml").exists()


def test_no_secret_value_or_reference_in_generated_files(provider: HostProvider) -> None:
    provider.generate_host([host(tailscale=tailscale_block())])
    for path in provider.ansible_dir.iterdir():
        text = path.read_text()
        assert AUTH_REF not in text
        assert SECRET_VALUE not in text
        assert "tailscale.oauth_client_id" not in text
    tailscale = _inventory(provider)["all"]["hosts"]["vps-01"]["infrafoundry_tailscale"]
    assert tailscale["hostname"] == "vps-01"
    assert tailscale["advertise_tags"] == ["tag:example"]
    assert tailscale["auth_mode"] == "oauth"


@pytest.mark.parametrize(
    ("resource", "fragment"),
    [
        (host(address=None), "address"),
        (host(address="-oProxyCommand=x"), "must not start with '-'"),
        (host(address="bad host"), "not an IP address or hostname"),
        (host(ssh_port=0), "ssh_port"),
        (host(ssh_port=70000), "ssh_port"),
        (host(ssh_port=True), "ssh_port"),
        (host(groups=["bad-group"]), "groups"),
        (host(ssh_user="-x"), "ssh_user"),
        (host(ansible={"playbooks": ["/etc/p.yml"]}), "relative path"),
        (host(ansible={"playbooks": ["../outside.yml"]}), "relative path"),
        (host(ansible={"playbooks": ["playbooks/missing.yml"]}), "does not exist"),
        (host(ansible={"playbooks": "base.yml"}), "list of paths"),
        (host(tailscale=tailscale_block(additional_parts=[{"content": "x"}])), "cloud-init only"),
        (host(tailscale={"advertise_tags": ["tag:example"]}), "auth"),
    ],
)
def test_invalid_hosts_are_rejected(provider: HostProvider, resource: Any, fragment: str) -> None:
    if "address" in resource.config and resource.config["address"] is None:
        del resource.config["address"]
    with pytest.raises(SchemaValidationError, match=fragment):
        provider.generate_host([resource])


def test_escaping_symlink_playbook_is_rejected(provider: HostProvider, repo: Path) -> None:
    outside = repo.parent / "outside-playbook.yml"
    outside.write_text("---\n")
    (repo / "playbooks" / "link.yml").symlink_to(outside)
    with pytest.raises(SchemaValidationError, match="outside the config repo"):
        provider.generate_host([host(ansible={"playbooks": ["playbooks/link.yml"]})])


def test_unknown_key_is_only_a_warning(provider: HostProvider) -> None:
    provider.generate_host([host(colour="red")])
    assert (provider.ansible_dir / "inventory.yml").exists()


def test_get_host_runs_order_and_auth_ref(provider: HostProvider, repo: Path) -> None:
    provider.generate_host(
        [
            host("a", ansible={"playbooks": ["playbooks/base.yml"]}, tailscale=tailscale_block()),
            host("b"),
        ]
    )
    runs = provider.get_host_runs()
    assert [r.name for r in runs] == ["a", "b"]
    enrollment = str(provider.ansible_dir / "tailscale.yml")
    assert runs[0].playbooks == (enrollment, str((repo / "playbooks" / "base.yml").resolve()))
    assert runs[0].tailscale_auth_ref == AUTH_REF
    assert runs[0].enrollment_playbook == enrollment
    assert runs[1].playbooks == ()
    assert runs[1].tailscale_auth_ref is None
    assert [r.name for r in provider.get_host_runs(["b"])] == ["b"]


def test_resolve_tailscale_auth(provider: HostProvider) -> None:
    env = make_env({"tailscale": {"oauth_client_secret": SECRET_VALUE}})
    with patch.object(HostProvider, "_load_environment_config", return_value=env):
        assert provider.resolve_tailscale_auth(AUTH_REF) == SECRET_VALUE


def test_resolve_tailscale_auth_missing_names_only_the_reference(provider: HostProvider) -> None:
    env = make_env({"tailscale": {"other": SECRET_VALUE}})
    with (
        patch.object(HostProvider, "_load_environment_config", return_value=env),
        pytest.raises(ValueError, match=AUTH_REF) as info,
    ):
        provider.resolve_tailscale_auth(AUTH_REF)
    assert SECRET_VALUE not in str(info.value)


def test_resolve_tailscale_auth_without_environment(provider: HostProvider) -> None:
    with (
        patch.object(HostProvider, "_load_environment_config", return_value=None),
        pytest.raises(ValueError, match=AUTH_REF),
    ):
        provider.resolve_tailscale_auth(AUTH_REF)


def test_name_key_is_known_and_raises_no_warning(provider: HostProvider) -> None:
    """The loader leaves ``name`` in the config dict; it must not read as unknown (#1411)."""
    from infrafoundry.providers.host.schema import check_host

    resource = host("vps-01")
    resource.config["name"] = "vps-01"
    assert check_host(resource, None) == []
