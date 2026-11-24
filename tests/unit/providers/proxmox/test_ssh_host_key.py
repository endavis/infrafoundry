"""Tests for pinned SSH host keys in the Proxmox provider (#1581)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.proxmox import ProxmoxProvider
from infrafoundry.providers.proxmox.validator import ProxmoxValidator

PUBLIC = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleSentinelPublicKey0"
SENTINEL_PRIVATE = (
    "-----BEGIN OPENSSH " + "PRIVATE KEY-----\n"
    "SENTINEL-NOT-A-REAL-KEY\n"
    "-----END OPENSSH " + "PRIVATE KEY-----\n"
)
TF_VAR = "package_proxmox_demo_ssh_host_keys_vm_01_ed25519_private"


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return config_dir, output_dir


@pytest.fixture
def provider(dirs: tuple[Path, Path]) -> ProxmoxProvider:
    p = ProxmoxProvider(*dirs)
    p.set_environment("test")
    return p


def _vm(
    name: str = "vm-01",
    *,
    host_key: bool = True,
    entry: dict[str, str] | None = None,
    secrets: dict[str, Any] | None = None,
    **config: Any,
) -> ResourceConfig:
    cfg: dict[str, Any] = {"name": name, "target_node": "node1", "vmid": 200, **config}
    if host_key:
        cfg["ssh_host_key"] = {"address": "192.0.2.10"}
    if secrets is None and entry is not None:
        secrets = {"ssh_host_keys": {name: entry}}
    return ResourceConfig(
        name=name,
        type="vm",
        provider="proxmox",
        config=cfg,
        package_name="demo",
        package_path="proxmox/demo",
        package_secrets=secrets,
    )


FULL = {"ed25519_private": SENTINEL_PRIVATE, "ed25519_public": PUBLIC}


def _tf(output_dir: Path, name: str = "vms.tf") -> str:
    return (output_dir / "test" / "terraform" / "proxmox" / name).read_text()


class TestGeneratedTerraform:
    def test_vms_tf_holds_the_expression_and_variable_is_sensitive(
        self, provider: ProxmoxProvider, dirs: tuple[Path, Path]
    ) -> None:
        _, output_dir = dirs
        provider.generate_terraform([_vm(entry=FULL)])

        vms = _tf(output_dir)
        assert "ssh_keys:" in vms
        assert f"ed25519_private: ${{jsonencode(var.{TF_VAR})}}" in vms
        assert f'ed25519_public: "{PUBLIC}"' in vms
        variables = _tf(output_dir, "variables.tf")
        assert f'variable "{TF_VAR}"' in variables
        block = variables[variables.index(f'variable "{TF_VAR}"') :].split("}")[0]
        assert "sensitive" in block

    def test_the_private_key_is_in_no_generated_file(
        self, provider: ProxmoxProvider, dirs: tuple[Path, Path]
    ) -> None:
        _, output_dir = dirs
        provider.generate_terraform([_vm(entry=FULL)])

        for path in (output_dir / "test").rglob("*"):
            if path.is_file():
                assert "SENTINEL" not in path.read_text(errors="ignore"), path

    def test_env_var_carries_the_private_key(
        self, provider: ProxmoxProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        resource = _vm(entry=FULL)
        provider.generate_terraform([resource])
        env = EnvironmentConfig(name="test", provider_settings={}, secrets={})
        monkeypatch.setattr(provider, "_load_environment_config", lambda: env)

        result = provider.get_terraform_env_vars()

        assert result[f"TF_VAR_{TF_VAR}"] == SENTINEL_PRIVATE

    def test_pinned_only_vm_is_byte_identical_to_one_without_the_field(
        self, dirs: tuple[Path, Path], tmp_path: Path
    ) -> None:
        outputs: dict[str, str] = {}
        for label, resource in (
            ("pinned", _vm(entry={"ed25519_public": PUBLIC})),
            ("plain", _vm(host_key=False)),
        ):
            out = tmp_path / label
            out.mkdir()
            p = ProxmoxProvider(dirs[0], out)
            p.set_environment("test")
            p.generate_terraform([resource])
            outputs[label] = _tf(out)
            assert "ssh_keys:" not in outputs[label]
        assert outputs["pinned"] == outputs["plain"]

    def test_user_snippet_expressions_stay_escaped_and_the_fragment_does_not(
        self, provider: ProxmoxProvider, dirs: tuple[Path, Path]
    ) -> None:
        config_dir, output_dir = dirs
        snippet = config_dir / "test" / "files" / "cloud-init-snippets" / "mine.yaml"
        snippet.parent.mkdir(parents=True)
        snippet.write_text("runcmd:\n  - echo ${USER}\n")

        provider.generate_terraform([_vm(entry=FULL, cloud_init_snippets=["mine"])])

        vms = _tf(output_dir)
        assert "echo $${USER}" in vms
        assert f"${{jsonencode(var.{TF_VAR})}}" in vms
        assert f"$${{jsonencode(var.{TF_VAR})}}" not in vms

    def test_generation_is_idempotent_across_both_calls(self, provider: ProxmoxProvider) -> None:
        resource = _vm(entry=FULL)
        once = provider._process_cloud_init_snippets(resource)
        twice = provider._process_cloud_init_snippets(once)
        assert once.config["cloud_init_user_data"] == twice.config["cloud_init_user_data"]
        assert (
            twice.config["terraform_secrets"].count("package.ssh_host_keys.vm-01.ed25519_private")
            == 1
        )


class TestRefusals:
    def test_tailscale_vm_is_refused(self, provider: ProxmoxProvider) -> None:
        vm = _vm(entry=FULL, tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}})
        with pytest.raises(SchemaValidationError, match="tailscale"):
            provider.generate_terraform([vm])

    def test_snippet_that_sets_ssh_keys_is_refused(
        self, provider: ProxmoxProvider, dirs: tuple[Path, Path]
    ) -> None:
        config_dir, _ = dirs
        snippet = config_dir / "test" / "files" / "cloud-init-snippets" / "keys.yaml"
        snippet.parent.mkdir(parents=True)
        snippet.write_text("ssh_keys:\n  ed25519_public: x\n")
        with pytest.raises(SchemaValidationError, match="ssh_keys"):
            provider.generate_terraform([_vm(entry=FULL, cloud_init_snippets=["keys"])])

    def test_malformed_private_key_is_refused(self, provider: ProxmoxProvider) -> None:
        vm = _vm(entry={"ed25519_private": "SENTINEL-garbage", "ed25519_public": PUBLIC})
        with pytest.raises(SchemaValidationError) as err:
            provider.generate_terraform([vm])
        assert "SENTINEL" not in str(err.value)


class TestValidateOffline:
    @staticmethod
    def _run(resources: list[ResourceConfig]) -> ValidationReport:
        report = ValidationReport()
        env = EnvironmentConfig(name="test", provider_settings={}, secrets={})
        ProxmoxValidator(env, report).validate_offline(resources)
        return report

    def test_missing_entry_is_an_error_naming_the_fix(self) -> None:
        report = self._run([_vm(secrets={})])
        failed = [r for r in report.results if not r.passed]
        assert [r.check_name for r in failed] == ["proxmox_ssh_host_key_vm-01"]
        assert "foundry secrets host-keys" in failed[0].message

    def test_ok_entries_pass_and_the_private_ref_resolves(self) -> None:
        assert not self._run([_vm(entry=FULL)]).has_errors()
        assert not self._run([_vm(entry={"ed25519_public": PUBLIC})]).has_errors()

    def test_tailscale_combination_is_an_error(self) -> None:
        vm = _vm(entry=FULL, tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}})
        assert any(
            r.check_name == "proxmox_ssh_host_key_vm-01"
            for r in self._run([vm]).results
            if not r.passed
        )

    def test_the_resource_is_not_changed(self) -> None:
        vm = _vm(entry=FULL)
        self._run([vm])
        assert "terraform_secrets" not in vm.config

    def test_resources_without_the_field_are_ignored(self) -> None:
        assert not self._run([_vm(host_key=False)]).has_errors()


def _generated_pair() -> tuple[str, str]:
    """An ed25519 OpenSSH private key and its public line, generated at test time."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.OpenSSH,
        serialization.NoEncryption(),
    ).decode()
    public = (
        key.public_key()
        .public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
        .decode()
    )
    return pem, public


def _dropbear_vm(pem: str, public: str) -> ResourceConfig:
    vm = _vm(
        entry={"ed25519_private": pem, "ed25519_public": public},
        disk_image_source="https://example.com/openwrt.img.gz",
    )
    vm.config["ssh_host_key"]["format"] = "dropbear"
    return vm


class TestDropbearFormat:
    """``format: dropbear`` keys never reach Terraform (#1650)."""

    def test_no_secret_ref_cloud_init_or_variable(
        self, provider: ProxmoxProvider, dirs: tuple[Path, Path]
    ) -> None:
        _, output_dir = dirs
        pem, public = _generated_pair()
        vm = _dropbear_vm(pem, public)

        provider.generate_terraform([vm])

        assert "terraform_secrets" not in vm.config
        body = pem.splitlines()[1]
        for path in (output_dir / "test").rglob("*"):
            if path.is_file():
                text = path.read_text(errors="ignore")
                assert body not in text, path
                assert "ssh_keys:" not in text, path
                assert "ed25519_private" not in text, path

    def test_a_mismatched_pair_is_a_validation_error(self) -> None:
        pem, _ = _generated_pair()
        _, other_public = _generated_pair()
        report = TestValidateOffline._run([_dropbear_vm(pem, other_public)])
        failed = [r for r in report.results if not r.passed]
        assert [r.check_name for r in failed] == ["proxmox_ssh_host_key_vm-01"]
        assert pem.splitlines()[1] not in failed[0].message

    def test_a_matching_pair_passes_and_a_missing_entry_names_the_fix(self) -> None:
        pem, public = _generated_pair()
        assert not TestValidateOffline._run([_dropbear_vm(pem, public)]).has_errors()
        vm = _dropbear_vm(pem, public)
        vm.package_secrets = {}
        report = TestValidateOffline._run([vm])
        failed = [r for r in report.results if not r.passed]
        assert "foundry secrets host-keys" in failed[0].message
