"""Tests for the OCI provider's Tailscale cloud-init module integration.

Phase 2 of issue #212. Verifies that resources with a ``tailscale:`` block
produce a ``module "tailscale_<name>"`` block in the generated terraform,
reference the right ``var.<sanitized>`` for auth, declare the
``hashicorp/cloudinit`` provider in ``provider.tf``, and that the existing
``cloud_init_snippets`` path is unchanged for resources without tailscale.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest

from infrafoundry.core.config.models import EnvironmentConfig
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.oci import OCIProvider


@pytest.fixture
def tmp_dirs(tmp_path: Path) -> Any:
    """Create temporary config and output directories."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return config_dir, output_dir


@pytest.fixture
def provider(tmp_dirs: Any) -> OCIProvider:
    """OCIProvider with the test environment set."""
    config_dir, output_dir = tmp_dirs
    p = OCIProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


def _instance(
    name: str, *, tailscale: dict[str, Any] | None = None, **extra_config: Any
) -> ResourceConfig:
    """Build a minimal OCI instance ResourceConfig with optional tailscale block."""
    config = {
        "shape": "VM.Standard.A1.Flex",
        "subnet": "public-subnet",
        "image": "ocid1.image.oc1.iad.example",
        **extra_config,
    }
    if tailscale is not None:
        config["tailscale"] = tailscale
    return ResourceConfig(name=name, type="instance", provider="oci", config=config)


def _read_tf(output_dir: Any, filename: str) -> str:
    return cast("str", (output_dir / "test" / "terraform" / "oci" / filename).read_text())


_SENTINEL_SECRET = "SENTINEL-OAUTH-SECRET"
_SENTINEL_KEY = "SENTINEL-AUTH-KEY"


def _module_block(tf: str, module_name: str) -> str:
    """Return the text of one ``module "<name>" { ... }`` block."""
    match = re.search(rf'module "{module_name}" \{{.*?^\}}', tf, re.DOTALL | re.MULTILINE)
    assert match is not None, f"module {module_name} not found"
    return match.group(0)


def _attr_assigned(block: str, attr: str) -> bool:
    """Return True if ``attr = <expr>`` is assigned in the block."""
    return re.search(rf"^\s*{attr}\s*=\s*\S+", block, re.MULTILINE) is not None


def _module_precondition_holds(block: str) -> bool:
    """Model the tailscale/cloudinit 0.0.11 auth precondition over a block.

    A ``var.*`` reference counts as non-empty, a missing attribute as empty.
    ``client_id`` / ``client_secret`` are only accepted with ``id_token`` or
    ``audience``; otherwise ``auth_key`` is required.
    """
    has_key = _attr_assigned(block, "auth_key")
    has_client = _attr_assigned(block, "client_id") or _attr_assigned(block, "client_secret")
    has_federation = _attr_assigned(block, "id_token") or _attr_assigned(block, "audience")
    if has_client:
        return has_federation
    return has_key


class TestOCITailscaleAuthKey:
    """Cover the static auth_key auth mode."""

    def test_module_block_emitted(self, provider: OCIProvider, tmp_dirs: Any) -> None:
        _, output_dir = tmp_dirs
        instance = _instance(
            "ts-control",
            tailscale={
                "enable_ssh": True,
                "advertise_tags": ["tag:k3s"],
                "auth": {"auth_key_secret": "tailscale.auth_key"},
            },
        )
        provider.generate_terraform([instance])
        instances_tf = _read_tf(output_dir, "instances.tf")

        assert 'module "tailscale_ts_control"' in instances_tf
        assert 'source  = "tailscale/tailscale/cloudinit"' in instances_tf
        assert 'version = "0.0.11"' in instances_tf
        assert "auth_key = var.tailscale_auth_key" in instances_tf
        # client_id/secret should NOT appear in auth_key mode
        assert "client_id" not in instances_tf
        assert "client_secret" not in instances_tf

    def test_user_data_uses_module_rendered(self, provider: OCIProvider, tmp_dirs: Any) -> None:
        _, output_dir = tmp_dirs
        instance = _instance(
            "ts-control",
            tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}},
        )
        provider.generate_terraform([instance])
        instances_tf = _read_tf(output_dir, "instances.tf")

        assert "user_data = module.tailscale_ts_control.rendered" in instances_tf
        # Existing cloud_init_merged path should NOT be used for this instance
        assert "cloud_init_merged" not in instances_tf

    def test_variables_tf_declares_sensitive_var(
        self, provider: OCIProvider, tmp_dirs: Any
    ) -> None:
        _, output_dir = tmp_dirs
        instance = _instance(
            "ts-control",
            tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}},
        )
        provider.generate_terraform([instance])
        variables_tf = _read_tf(output_dir, "variables.tf")

        assert 'variable "tailscale_auth_key"' in variables_tf
        assert "sensitive   = true" in variables_tf

    def test_advertise_tags_rendered(self, provider: OCIProvider, tmp_dirs: Any) -> None:
        _, output_dir = tmp_dirs
        instance = _instance(
            "ts-control",
            tailscale={
                "advertise_tags": ["tag:infra", "tag:k3s"],
                "auth": {"auth_key_secret": "tailscale.auth_key"},
            },
        )
        provider.generate_terraform([instance])
        instances_tf = _read_tf(output_dir, "instances.tf")

        assert "advertise_tags" in instances_tf
        assert "tag:infra" in instances_tf
        assert "tag:k3s" in instances_tf


class TestOCITailscaleOAuth:
    """Cover the OAuth client credentials auth mode.

    The cloudinit module has no OAuth mode of its own, so the OAuth client
    secret is passed as ``auth_key`` (issue #1311).
    """

    @staticmethod
    def _oauth_resource() -> ResourceConfig:
        return _instance(
            "ts-control",
            tailscale={
                "advertise_tags": ["tag:example"],
                "auth": {
                    "oauth": {
                        "client_id_secret": "tailscale.oauth_client_id",
                        "client_secret_secret": "tailscale.oauth_client_secret",
                    },
                },
            },
        )

    def test_oauth_module_block_emitted(self, provider: OCIProvider, tmp_dirs: Any) -> None:
        _, output_dir = tmp_dirs
        provider.generate_terraform([self._oauth_resource()])
        instances_tf = _read_tf(output_dir, "instances.tf")

        assert 'module "tailscale_ts_control"' in instances_tf
        block = _module_block(instances_tf, "tailscale_ts_control")
        assert "auth_key = var.tailscale_oauth_client_secret" in block
        assert re.search(r"^\s*client_id\s*=", block, re.MULTILINE) is None
        assert re.search(r"^\s*client_secret\s*=", block, re.MULTILINE) is None
        assert "tailscale_oauth_client_id" not in instances_tf

    def test_oauth_variables_tf_has_only_client_secret(
        self, provider: OCIProvider, tmp_dirs: Any
    ) -> None:
        _, output_dir = tmp_dirs
        provider.generate_terraform([self._oauth_resource()])
        variables_tf = _read_tf(output_dir, "variables.tf")

        assert 'variable "tailscale_oauth_client_id"' not in variables_tf
        assert 'variable "tailscale_oauth_client_secret"' in variables_tf

    def test_oauth_without_client_id_secret_renders(
        self, provider: OCIProvider, tmp_dirs: Any
    ) -> None:
        _, output_dir = tmp_dirs
        resource = _instance(
            "ts-control",
            tailscale={
                "advertise_tags": ["tag:example"],
                "auth": {"oauth": {"client_secret_secret": "tailscale.oauth_client_secret"}},
            },
        )
        provider.generate_terraform([resource])
        block = _module_block(_read_tf(output_dir, "instances.tf"), "tailscale_ts_control")
        assert "auth_key = var.tailscale_oauth_client_secret" in block


class TestOCITailscaleModulePrecondition:
    """The rendered module block satisfies the cloudinit module's auth precondition."""

    def test_oauth_mode_satisfies_precondition(self, provider: OCIProvider, tmp_dirs: Any) -> None:
        _, output_dir = tmp_dirs
        provider.generate_terraform([TestOCITailscaleOAuth._oauth_resource()])
        block = _module_block(_read_tf(output_dir, "instances.tf"), "tailscale_ts_control")
        assert _module_precondition_holds(block)

    def test_auth_key_mode_satisfies_precondition(
        self, provider: OCIProvider, tmp_dirs: Any
    ) -> None:
        _, output_dir = tmp_dirs
        resource = _instance(
            "ts-control",
            tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}},
        )
        provider.generate_terraform([resource])
        block = _module_block(_read_tf(output_dir, "instances.tf"), "tailscale_ts_control")
        assert _module_precondition_holds(block)

    def test_precondition_model_rejects_old_oauth_output(self) -> None:
        old = 'module "m" {\n  client_id     = var.a\n  client_secret = var.b\n}'
        assert not _module_precondition_holds(old)


class TestOCITailscaleSecretSafety:
    """Secret values reach Terraform only through TF_VAR_*, never .tf files."""

    @pytest.mark.parametrize("mode", ["oauth", "auth_key"])
    def test_no_secret_in_generated_files(
        self, provider: OCIProvider, tmp_dirs: Any, mode: str
    ) -> None:
        _, output_dir = tmp_dirs
        if mode == "oauth":
            resource = TestOCITailscaleOAuth._oauth_resource()
        else:
            resource = _instance(
                "ts-control", tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}}
            )
        provider.generate_terraform([resource])

        for tf_file in (output_dir / "test" / "terraform" / "oci").glob("*.tf"):
            text = tf_file.read_text()
            assert _SENTINEL_SECRET not in text
            assert _SENTINEL_KEY not in text

    def test_oauth_env_vars_carry_secret_only(
        self, provider: OCIProvider, tmp_dirs: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        resource = TestOCITailscaleOAuth._oauth_resource()
        provider.generate_terraform([resource])
        env = EnvironmentConfig(
            name="test",
            provider_settings={},
            secrets={
                "tailscale": {
                    "oauth_client_id": "SENTINEL-OAUTH-ID",
                    "oauth_client_secret": _SENTINEL_SECRET,
                }
            },
        )
        monkeypatch.setattr(provider, "_load_environment_config", lambda: env)

        result = provider.get_terraform_env_vars()

        assert result == {"TF_VAR_tailscale_oauth_client_secret": _SENTINEL_SECRET}


class TestOCITailscaleAdditionalParts:
    """Cover the ``additional_parts`` escape hatch."""

    def test_additional_parts_rendered(self, provider: OCIProvider, tmp_dirs: Any) -> None:
        _, output_dir = tmp_dirs
        instance = _instance(
            "ts-control",
            tailscale={
                "auth": {"auth_key_secret": "tailscale.auth_key"},
                "additional_parts": [
                    {
                        "filename": "99-extras.cfg",
                        "content_type": "text/cloud-config",
                        "content": "bootcmd:\n  - ssh-keygen -A\n",
                    },
                ],
            },
        )
        provider.generate_terraform([instance])
        instances_tf = _read_tf(output_dir, "instances.tf")

        assert "additional_parts" in instances_tf
        assert "99-extras.cfg" in instances_tf
        assert "ssh-keygen -A" in instances_tf


class TestOCITailscaleValidation:
    """Cover schema enforcement (mutual exclusion, both auth modes)."""

    def test_both_auth_modes_rejected(self, provider: OCIProvider, tmp_dirs: Any) -> None:
        from infrafoundry.core.tailscale import TailscaleSchemaError

        instance = _instance(
            "ts-control",
            tailscale={
                "auth": {
                    "auth_key_secret": "tailscale.auth_key",
                    "oauth": {
                        "client_id_secret": "tailscale.oauth_client_id",
                        "client_secret_secret": "tailscale.oauth_client_secret",
                    },
                },
            },
        )

        with pytest.raises(TailscaleSchemaError, match="exactly one"):
            provider.generate_terraform([instance])

    def test_no_auth_mode_rejected(self, provider: OCIProvider, tmp_dirs: Any) -> None:
        from infrafoundry.core.tailscale import TailscaleSchemaError

        instance = _instance("ts-control", tailscale={"auth": {}})

        with pytest.raises(TailscaleSchemaError, match="exactly one"):
            provider.generate_terraform([instance])

    def test_tailscale_and_cloud_init_snippets_rejected(
        self, provider: OCIProvider, tmp_dirs: Any
    ) -> None:
        from infrafoundry.core.tailscale import TailscaleSchemaError

        instance = _instance(
            "ts-control",
            tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}},
            cloud_init_snippets=["base"],
        )

        with pytest.raises(TailscaleSchemaError, match="mutually exclusive"):
            provider.generate_terraform([instance])

    def test_invalid_tag_format_rejected(self, provider: OCIProvider, tmp_dirs: Any) -> None:
        from infrafoundry.core.tailscale import TailscaleSchemaError

        instance = _instance(
            "ts-control",
            tailscale={
                "advertise_tags": ["k3s"],  # Missing 'tag:' prefix
                "auth": {"auth_key_secret": "tailscale.auth_key"},
            },
        )

        with pytest.raises(TailscaleSchemaError, match="must start with 'tag:'"):
            provider.generate_terraform([instance])


class TestOCITailscaleMultipleInstances:
    """Cover deduplication when multiple instances share the same auth secret."""

    def test_multiple_instances_one_var_declaration(
        self, provider: OCIProvider, tmp_dirs: Any
    ) -> None:
        _, output_dir = tmp_dirs
        instances = [
            _instance(
                "ts-a",
                tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}},
            ),
            _instance(
                "ts-b",
                tailscale={"auth": {"auth_key_secret": "tailscale.auth_key"}},
            ),
        ]
        provider.generate_terraform(instances)

        instances_tf = _read_tf(output_dir, "instances.tf")
        variables_tf = _read_tf(output_dir, "variables.tf")

        # Two separate module blocks
        assert 'module "tailscale_ts_a"' in instances_tf
        assert 'module "tailscale_ts_b"' in instances_tf

        # But the variable is declared exactly once
        assert variables_tf.count('variable "tailscale_auth_key"') == 1


class TestOCITailscaleRegression:
    """Cover that the existing cloud_init_snippets path still works."""

    def test_instance_without_tailscale_uses_existing_path(
        self, provider: OCIProvider, tmp_dirs: Any
    ) -> None:
        config_dir, output_dir = tmp_dirs
        snippets_dir = config_dir / "test" / "files" / "cloud-init-snippets"
        snippets_dir.mkdir(parents=True)
        (snippets_dir / "base.yaml").write_text("packages:\n  - curl\n")

        instance = _instance("plain", cloud_init_snippets=["base"])
        provider.generate_terraform([instance])
        instances_tf = _read_tf(output_dir, "instances.tf")

        # Existing path: base64encode + cloud-config heredoc
        assert "base64encode" in instances_tf
        # Should NOT have a module block
        assert 'module "tailscale_' not in instances_tf

    def test_provider_tf_declares_cloudinit_provider_unconditionally(
        self, provider: OCIProvider, tmp_dirs: Any
    ) -> None:
        _, output_dir = tmp_dirs
        # Even without any tailscale-using instance, the provider declaration
        # is unconditional (simpler than gating on instance content).
        instance = _instance("plain")
        provider.generate_terraform([instance])
        provider_tf = _read_tf(output_dir, "provider.tf")

        assert 'source  = "hashicorp/cloudinit"' in provider_tf
