"""Tests for pinned SSH host keys on OCI instances with Tailscale (#1583)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationReport
from infrafoundry.providers.oci import OCIProvider
from infrafoundry.providers.oci.validator import OCIValidator

PUBLIC = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleSentinelPublicKey0"
SENTINEL_PRIVATE = (
    "-----BEGIN OPENSSH " + "PRIVATE KEY-----\n"
    "SENTINEL-NOT-A-REAL-KEY\n"
    "-----END OPENSSH " + "PRIVATE KEY-----\n"
)
TF_VAR = "package_oci_demo_ssh_host_keys_ts_control_ed25519_private"
FULL = {"ed25519_private": SENTINEL_PRIVATE, "ed25519_public": PUBLIC}
TAILSCALE = {
    "advertise_tags": ["tag:example"],
    "auth": {
        "oauth": {
            "client_id_secret": "tailscale.oauth_client_id",
            "client_secret_secret": "tailscale.oauth_client_secret",
        }
    },
}


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return config_dir, output_dir


@pytest.fixture
def provider(dirs: tuple[Path, Path]) -> OCIProvider:
    p = OCIProvider(*dirs)
    p.set_environment("test")
    return p


def _instance(
    *,
    host_key: bool = True,
    entry: dict[str, str] | None = None,
    secrets: dict[str, Any] | None = None,
    tailscale: dict[str, Any] | None = TAILSCALE,
) -> ResourceConfig:
    name = "ts-control"
    cfg: dict[str, Any] = {
        "shape": "VM.Standard.A1.Flex",
        "subnet": "public-subnet",
        "image": "ocid1.image.oc1.iad.example",
    }
    if tailscale is not None:
        cfg["tailscale"] = tailscale
    if host_key:
        cfg["ssh_host_key"] = {"address": "ts-control.example.net"}
    if secrets is None and entry is not None:
        secrets = {"ssh_host_keys": {name: entry}}
    return ResourceConfig(
        name=name,
        type="instance",
        provider="oci",
        config=cfg,
        package_name="demo",
        package_path="oci/demo",
        package_secrets=secrets,
    )


def _tf(output_dir: Path, name: str = "instances.tf") -> str:
    return (output_dir / "test" / "terraform" / "oci" / name).read_text()


class TestGeneratedTerraform:
    def test_module_part_holds_the_expression_and_variable_is_sensitive(
        self, provider: OCIProvider, dirs: tuple[Path, Path]
    ) -> None:
        _, output_dir = dirs
        provider.generate_terraform([_instance(entry=FULL)])

        instances = _tf(output_dir)
        assert 'content_type = "text/cloud-config"' in instances
        assert f"ed25519_private: ${{jsonencode(var.{TF_VAR})}}" in instances
        assert f'ed25519_public: "{PUBLIC}"' in instances
        variables = _tf(output_dir, "variables.tf")
        block = variables[variables.index(f'variable "{TF_VAR}"') :].split("}")[0]
        assert "sensitive" in block

    def test_the_private_key_is_in_no_generated_file(
        self, provider: OCIProvider, dirs: tuple[Path, Path]
    ) -> None:
        _, output_dir = dirs
        provider.generate_terraform([_instance(entry=FULL)])
        for path in (output_dir / "test").rglob("*"):
            if path.is_file():
                assert "SENTINEL" not in path.read_text(errors="ignore"), path

    def test_env_var_carries_the_private_key(
        self, provider: OCIProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider.generate_terraform([_instance(entry=FULL)])
        env = EnvironmentConfig(
            name="test",
            provider_settings={},
            secrets={
                "tailscale": {"oauth_client_id": "id", "oauth_client_secret": "secret"},
            },
        )
        monkeypatch.setattr(provider, "_load_environment_config", lambda: env)

        assert provider.get_terraform_env_vars()[f"TF_VAR_{TF_VAR}"] == SENTINEL_PRIVATE

    def test_pinned_only_instance_is_byte_identical_to_one_without_the_field(
        self, dirs: tuple[Path, Path], tmp_path: Path
    ) -> None:
        outputs: dict[str, tuple[str, str]] = {}
        for label, resource in (
            ("pinned", _instance(entry={"ed25519_public": PUBLIC})),
            ("plain", _instance(host_key=False)),
        ):
            out = tmp_path / label
            out.mkdir()
            p = OCIProvider(dirs[0], out)
            p.set_environment("test")
            p.generate_terraform([resource])
            outputs[label] = (_tf(out), _tf(out, "variables.tf"))
            assert "ssh_keys:" not in outputs[label][0]
        assert outputs["pinned"] == outputs["plain"]

    def test_user_parts_are_kept_and_the_host_key_part_comes_after(
        self, provider: OCIProvider, dirs: tuple[Path, Path]
    ) -> None:
        _, output_dir = dirs
        ts = {
            **TAILSCALE,
            "additional_parts": [
                {
                    "filename": "mine.sh",
                    "content_type": "text/x-shellscript",
                    "content": "#!/bin/sh",
                }
            ],
        }
        provider.generate_terraform([_instance(entry=FULL, tailscale=ts)])
        instances = _tf(output_dir)
        assert instances.index("mine.sh") < instances.index("infrafoundry-ssh-host-key.cfg")

    def test_generation_is_idempotent(self, provider: OCIProvider) -> None:
        resource = _instance(entry=FULL)
        once = provider._process_cloud_init_snippets(resource)
        twice = provider._process_cloud_init_snippets(once)
        assert (
            once.config["tailscale_module_config"]["additional_parts"]
            == twice.config["tailscale_module_config"]["additional_parts"]
        )
        assert len(once.config["tailscale_module_config"]["additional_parts"]) == 1
        refs = twice.config["terraform_secrets"]
        assert refs.count("package.ssh_host_keys.ts-control.ed25519_private") == 1
        assert re.search(r"ssh_host_keys", " ".join(refs))


class TestRefusals:
    def test_without_tailscale_is_refused(self, provider: OCIProvider) -> None:
        with pytest.raises(SchemaValidationError, match="needs a 'tailscale' block"):
            provider.generate_terraform([_instance(entry=FULL, tailscale=None)])

    def test_cloud_config_part_that_sets_ssh_keys_is_refused(self, provider: OCIProvider) -> None:
        ts = {
            **TAILSCALE,
            "additional_parts": [
                {
                    "filename": "keys.cfg",
                    "content_type": "text/cloud-config",
                    "content": "#cloud-config\nssh_keys:\n  ed25519_public: x\n",
                }
            ],
        }
        with pytest.raises(SchemaValidationError, match="ssh_keys"):
            provider.generate_terraform([_instance(entry=FULL, tailscale=ts)])

    def test_malformed_private_key_is_refused(self, provider: OCIProvider) -> None:
        resource = _instance(
            entry={"ed25519_private": "SENTINEL-garbage", "ed25519_public": PUBLIC}
        )
        with pytest.raises(SchemaValidationError) as err:
            provider.generate_terraform([resource])
        assert "SENTINEL" not in str(err.value)


class TestValidateOffline:
    @staticmethod
    def _run(resources: list[ResourceConfig]) -> ValidationReport:
        report = ValidationReport()
        env = EnvironmentConfig(name="test", provider_settings={}, secrets={})
        OCIValidator(env, report).validate_offline(resources)
        return report

    def test_missing_entry_is_an_error_naming_the_fix(self) -> None:
        failed = [r for r in self._run([_instance(secrets={})]).results if not r.passed]
        names = [r.check_name for r in failed]
        assert "oci_ssh_host_key_ts-control" in names
        message = next(r.message for r in failed if r.check_name == "oci_ssh_host_key_ts-control")
        assert "foundry secrets host-keys" in message

    def test_full_and_pinned_entries_pass(self) -> None:
        for entry in (FULL, {"ed25519_public": PUBLIC}):
            failed = [
                r
                for r in self._run([_instance(entry=entry)]).results
                if not r.passed and "ssh_host_key" in r.check_name
            ]
            assert failed == []

    def test_without_tailscale_is_an_error(self) -> None:
        report = self._run([_instance(entry=FULL, tailscale=None)])
        assert any(
            r.check_name == "oci_ssh_host_key_ts-control" and "tailscale" in r.message
            for r in report.results
            if not r.passed
        )

    def test_the_resource_is_not_changed(self) -> None:
        resource = _instance(entry=FULL)
        self._run([resource])
        refs = resource.config.get("terraform_secrets", [])
        assert not [r for r in refs if "ssh_host_keys" in r]

    def test_instances_without_the_field_are_ignored(self) -> None:
        report = self._run([_instance(host_key=False)])
        assert not [r for r in report.results if "ssh_host_key" in r.check_name]
