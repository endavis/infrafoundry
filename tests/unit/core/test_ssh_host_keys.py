"""Tests for the pure SSH host key helpers (#1581)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.ssh_host_keys import (
    HOST_KEYS_VARIABLE,
    apply_host_key,
    cloud_config_fragment,
    host_key_config,
    host_key_entry,
    host_key_problems,
    known_hosts_value,
    private_key_ref,
    rebuild_problems,
)

PUBLIC = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleSentinelPublicKey0"
PUBLIC_B = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleSentinelPublicKey1"
# An obvious sentinel, never a real key.
SENTINEL_PRIVATE = (
    "-----BEGIN OPENSSH " + "PRIVATE KEY-----\n"
    "SENTINEL-NOT-A-REAL-KEY\n"
    "-----END OPENSSH " + "PRIVATE KEY-----\n"
)


def _vm(
    name: str = "vm-01",
    *,
    address: str | None = "192.0.2.10",
    secrets: dict[str, Any] | None = None,
    package: bool = True,
    **config: Any,
) -> ResourceConfig:
    cfg: dict[str, Any] = {"name": name, **config}
    if address is not None:
        cfg["ssh_host_key"] = {"address": address}
    return ResourceConfig(
        name=name,
        type="vm",
        provider="proxmox",
        config=cfg,
        package_name="demo" if package else None,
        package_path="proxmox/demo" if package else None,
        package_secrets=secrets,
    )


def _secrets(name: str = "vm-01", **entry: str) -> dict[str, Any]:
    return {HOST_KEYS_VARIABLE: {name: entry}}


FULL = {"ed25519_private": SENTINEL_PRIVATE, "ed25519_public": PUBLIC}


class TestConfig:
    def test_absent_is_none(self) -> None:
        assert host_key_config(_vm(address=None)) is None

    def test_valid(self) -> None:
        spec = host_key_config(_vm(address=" 192.0.2.10 "))
        assert spec is not None
        assert spec.address == "192.0.2.10"

    @pytest.mark.parametrize("address", ["", "  ", "a b", "a;b", "$(id)", "a/b"])
    def test_invalid_address(self, address: str) -> None:
        with pytest.raises(ValueError, match="ssh_host_key"):
            host_key_config(_vm(address=address))

    def test_not_a_mapping(self) -> None:
        resource = _vm(address=None)
        resource.config["ssh_host_key"] = "192.0.2.10"
        with pytest.raises(ValueError, match="mapping"):
            host_key_config(resource)


class TestEntry:
    def test_missing(self) -> None:
        assert host_key_entry(_vm()) == (None, False)
        assert host_key_entry(_vm(secrets={})) == (None, False)

    def test_pinned_only(self) -> None:
        resource = _vm(secrets=_secrets(ed25519_public=PUBLIC))
        assert host_key_entry(resource) == (PUBLIC, False)

    def test_full_never_returns_the_private_key(self) -> None:
        public, has_private = host_key_entry(_vm(secrets={HOST_KEYS_VARIABLE: {"vm-01": FULL}}))
        assert (public, has_private) == (PUBLIC, True)


class TestApply:
    def test_adds_ref_only_with_a_private_key(self) -> None:
        pinned = _vm(secrets=_secrets(ed25519_public=PUBLIC))
        assert apply_host_key(pinned) is None
        assert "terraform_secrets" not in pinned.config

    def test_full_adds_ref_and_is_idempotent(self) -> None:
        resource = _vm(secrets=_secrets(**FULL), terraform_secrets=["other.token"])
        first = apply_host_key(resource)
        second = apply_host_key(resource)
        assert first == second
        assert first is not None
        tf_var, public = first
        assert public == PUBLIC
        assert tf_var == "package_proxmox_demo_ssh_host_keys_vm_01_ed25519_private"
        assert resource.config["terraform_secrets"] == ["other.token", private_key_ref("vm-01")]

    def test_no_field_or_no_package(self) -> None:
        assert apply_host_key(_vm(address=None, secrets=_secrets(**FULL))) is None
        assert apply_host_key(_vm(secrets=_secrets(**FULL), package=False)) is None

    def test_public_missing_adds_nothing(self) -> None:
        resource = _vm(secrets=_secrets(ed25519_private=SENTINEL_PRIVATE))
        assert apply_host_key(resource) is None


class TestFragment:
    def test_parses_and_holds_an_expression_not_a_value(self) -> None:
        fragment = cloud_config_fragment("package_x_key", PUBLIC)
        data = yaml.safe_load(fragment)
        assert data["ssh_keys"]["ed25519_private"] == "${jsonencode(var.package_x_key)}"
        assert data["ssh_keys"]["ed25519_public"] == PUBLIC
        assert "BEGIN" not in fragment


class TestKnownHosts:
    def test_lines_are_joined_with_semicolons(self) -> None:
        a = _vm("vm-a", address="192.0.2.10", secrets=_secrets("vm-a", ed25519_public=PUBLIC))
        b = _vm(
            "vm-b",
            address="192.0.2.11",
            secrets=_secrets("vm-b", **FULL | {"ed25519_public": PUBLIC_B}),
        )
        assert known_hosts_value([a, b]) == (f"vm-a,192.0.2.10 {PUBLIC};vm-b,192.0.2.11 {PUBLIC_B}")

    def test_name_equal_to_address_is_not_duplicated(self) -> None:
        vm = _vm(
            "host.example.com",
            address="host.example.com",
            secrets=_secrets("host.example.com", ed25519_public=PUBLIC),
        )
        assert known_hosts_value([vm]) == f"host.example.com {PUBLIC}"

    def test_skips_resources_without_the_field_or_the_key(self) -> None:
        plain = _vm("plain", address=None)
        nokey = _vm("nokey", secrets={})
        bad = _vm("bad", secrets=_secrets("bad", ed25519_public="ssh-rsa AAAA"))
        assert known_hosts_value([plain, nokey, bad]) == ""

    def test_no_private_key_in_the_value(self) -> None:
        vm = _vm(secrets=_secrets(**FULL))
        assert "BEGIN" not in known_hosts_value([vm])


class TestProblems:
    def test_none_without_the_field(self) -> None:
        assert host_key_problems(_vm(address=None)) == []

    def test_ok(self) -> None:
        assert host_key_problems(_vm(secrets=_secrets(**FULL))) == []
        assert host_key_problems(_vm(secrets=_secrets(ed25519_public=PUBLIC))) == []

    def test_missing_entry_names_the_fix(self) -> None:
        (problem,) = host_key_problems(_vm(secrets={}))
        assert "vm-01" in problem
        assert "demo" in problem
        assert "foundry secrets host-keys --env" in problem

    def test_missing_entry_can_be_left_to_validation(self) -> None:
        assert host_key_problems(_vm(secrets={}), require_entry=False) == []

    def test_no_secrets_file(self) -> None:
        (problem,) = host_key_problems(_vm(secrets=None))
        assert "foundry secrets host-keys" in problem

    def test_malformed_public_key(self) -> None:
        problems = host_key_problems(_vm(secrets=_secrets(ed25519_public="ssh-rsa AAAA")))
        assert any("ed25519_public" in p for p in problems)

    def test_missing_public_key(self) -> None:
        problems = host_key_problems(_vm(secrets=_secrets(ed25519_private=SENTINEL_PRIVATE)))
        assert any("ed25519_public' is missing" in p for p in problems)

    def test_malformed_private_key(self) -> None:
        problems = host_key_problems(
            _vm(secrets=_secrets(ed25519_public=PUBLIC, ed25519_private="SENTINEL-garbage"))
        )
        assert any("ed25519_private" in p for p in problems)

    def test_snippet_that_sets_ssh_keys(self) -> None:
        problems = host_key_problems(_vm(secrets=_secrets(**FULL)), {"ssh_keys": {}})
        assert any("ssh_keys" in p for p in problems)

    def test_tailscale_is_unsupported(self) -> None:
        problems = host_key_problems(_vm(secrets=_secrets(**FULL), tailscale={"auth": {}}))
        assert any("tailscale" in p and "#1583" in p for p in problems)

    def test_tailscale_is_allowed_for_oci(self) -> None:
        resource = _vm(secrets=_secrets(**FULL), tailscale={"auth": {}})
        assert host_key_problems(resource, allow_tailscale=True) == []

    def test_not_from_a_package(self) -> None:
        (problem,) = host_key_problems(_vm(secrets=_secrets(**FULL), package=False))
        assert "package" in problem

    def test_invalid_address_is_a_problem(self) -> None:
        (problem,) = host_key_problems(_vm(address="a b"))
        assert "address" in problem

    def test_no_message_contains_a_key(self) -> None:
        cases = [
            _vm(secrets=_secrets(ed25519_public="ssh-rsa AAAA", ed25519_private=SENTINEL_PRIVATE)),
            _vm(secrets=_secrets(ed25519_public=PUBLIC, ed25519_private="SENTINEL-garbage")),
            _vm(secrets=_secrets(ed25519_private=SENTINEL_PRIVATE)),
            _vm(secrets={}),
        ]
        for resource in cases:
            text = "\n".join(host_key_problems(resource, {"ssh_keys": {}}))
            assert "SENTINEL" not in text
            assert "AAAA" not in text


class TestCloudConfigPart:
    def test_part_holds_the_expression_and_no_private_key(self) -> None:
        from infrafoundry.core.ssh_host_keys import cloud_config_part

        part = cloud_config_part("tf_var_x", "ssh-ed25519 AAAA")
        assert part["filename"] == "infrafoundry-ssh-host-key.cfg"
        assert part["content_type"] == "text/cloud-config"
        assert part["content"].startswith("#cloud-config\nssh_keys:\n")
        assert "${jsonencode(var.tf_var_x)}" in part["content"]
        assert "PRIVATE KEY" not in part["content"]


class TestRebuildProblems:
    def test_public_only_undeployed_is_reported(self) -> None:
        vm = _vm(secrets=_secrets(ed25519_public=PUBLIC))

        problems = rebuild_problems([vm], lambda _r: False, "dev")

        assert len(problems) == 1
        assert "vm-01" in problems[0]
        assert "demo" in problems[0]
        assert "--env dev --regenerate vm-01" in problems[0]

    @pytest.mark.parametrize("state", [True, None])
    def test_deployed_or_unknown_is_not_reported(self, state: bool | None) -> None:
        vm = _vm(secrets=_secrets(ed25519_public=PUBLIC))

        assert rebuild_problems([vm], lambda _r: state, "dev") == []

    def test_full_pair_missing_entry_and_no_pin_do_not_call_deployed(self) -> None:
        deployed = MagicMock(return_value=False)
        resources = [
            _vm("a", secrets=_secrets("a", **FULL)),
            _vm("b", secrets=None),
            _vm("c", address=None, secrets=_secrets("c", ed25519_public=PUBLIC)),
        ]

        assert rebuild_problems(resources, deployed, "dev") == []
        deployed.assert_not_called()

    def test_invalid_block_is_skipped(self) -> None:
        vm = _vm(secrets=_secrets(ed25519_public=PUBLIC))
        assert vm.config is not None
        vm.config["ssh_host_key"] = "nope"

        assert rebuild_problems([vm], lambda _r: False, "dev") == []

    def test_messages_hold_no_key_material(self) -> None:
        vm = _vm(secrets=_secrets(ed25519_public=PUBLIC))

        text = "\n".join(rebuild_problems([vm], lambda _r: False, "dev"))

        assert PUBLIC not in text
        assert "SENTINEL-NOT-A-REAL-KEY" not in text
