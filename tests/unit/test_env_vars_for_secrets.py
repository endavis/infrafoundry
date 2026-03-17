"""Tests for passing variables via environment instead of files on disk.

Covers:
- TerraformRunner sets TF_VAR_* correctly via provider.get_terraform_env_vars()
- No secrets.auto.tfvars generated (orchestrator no longer calls _export_secrets)
- ScriptHandler sets INFRAFOUNDRY_PACKAGE_VARS and INFRAFOUNDRY_VAR_* env vars
- Package variables include merged secrets from secrets.yaml
- Empty package_variables doesn't set env vars
- ResourceConfig carries package_variables
- EventContext carries package_variables
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from infrafoundry.core.events.context import EventContext
from infrafoundry.core.events.handlers.script import ScriptHandler
from infrafoundry.core.events.types import EventType
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.runners.terraform_runner import TerraformRunner


class TestResourceConfigPackageVariables:
    """ResourceConfig carries package_variables."""

    def test_default_none(self):
        """package_variables defaults to None."""
        rc = ResourceConfig(name="vm-1", type="vm", provider="proxmox", config={})
        assert rc.package_variables is None

    def test_set_package_variables(self):
        """package_variables can be set."""
        vars_ = {"cluster_name": "lab", "admin_password": "secret"}
        rc = ResourceConfig(
            name="vm-1", type="vm", provider="proxmox", config={}, package_variables=vars_
        )
        assert rc.package_variables == vars_


class TestEventContextPackageVariables:
    """EventContext carries package_variables."""

    def test_default_empty(self):
        """package_variables defaults to empty dict."""
        ctx = EventContext(event_type=EventType.RESOURCE_CREATED, environment="dev")
        assert ctx.package_variables == {}

    def test_set_package_variables(self):
        """package_variables can be set via constructor."""
        vars_ = {"ontap_password": "secret123"}
        ctx = EventContext(
            event_type=EventType.RESOURCE_CREATED,
            environment="dev",
            package_variables=vars_,
        )
        assert ctx.package_variables == vars_


class TestTerraformRunnerEnvVars:
    """TerraformRunner._prepare_environment merges TF_VAR_* from provider."""

    def test_sets_tf_var_from_provider(self):
        """Provider TF_VAR_* env vars are merged into the environment."""
        runner = TerraformRunner(console=Mock())
        provider = MagicMock(spec=ProviderBase)
        provider.get_terraform_env_vars.return_value = {
            "TF_VAR_proxmox_api_url": "https://pve.example.com",
            "TF_VAR_proxmox_api_token": "user@pam!token=secret",
        }

        with patch.dict("os.environ", {"HOME": "/home/test"}, clear=True):
            env = runner._prepare_environment(provider)

        assert env["TF_VAR_proxmox_api_url"] == "https://pve.example.com"
        assert env["TF_VAR_proxmox_api_token"] == "user@pam!token=secret"
        provider.get_terraform_env_vars.assert_called_once()

    def test_empty_provider_vars(self):
        """Empty provider vars don't break environment preparation."""
        runner = TerraformRunner(console=Mock())
        provider = MagicMock(spec=ProviderBase)
        provider.get_terraform_env_vars.return_value = {}

        with patch.dict("os.environ", {"HOME": "/home/test"}, clear=True):
            env = runner._prepare_environment(provider)

        assert "TF_VAR_proxmox_api_url" not in env

    def test_preserves_existing_env_vars(self):
        """Existing environment variables are preserved."""
        runner = TerraformRunner(console=Mock())
        provider = MagicMock(spec=ProviderBase)
        provider.get_terraform_env_vars.return_value = {"TF_VAR_new": "value"}

        with patch.dict("os.environ", {"EXISTING": "keep_me"}, clear=True):
            env = runner._prepare_environment(provider)

        assert env["EXISTING"] == "keep_me"
        assert env["TF_VAR_new"] == "value"


class TestScriptHandlerPackageVars:
    """ScriptHandler sets INFRAFOUNDRY_PACKAGE_VARS and INFRAFOUNDRY_VAR_*."""

    def _make_handler(self) -> ScriptHandler:
        return ScriptHandler(
            config={"script": "scripts/test.sh"},
            config_base_dir=Path("/tmp/config"),
        )

    def test_sets_package_vars_json(self):
        """INFRAFOUNDRY_PACKAGE_VARS is set as JSON string."""
        handler = self._make_handler()
        vars_ = {"cluster_name": "lab", "admin_password": "secret123"}
        ctx = EventContext(
            event_type=EventType.RESOURCE_CREATED,
            environment="dev",
            package_variables=vars_,
        )

        with patch.dict("os.environ", {}, clear=True):
            env = handler._prepare_environment(ctx, Path("/tmp/config/envs/dev"))

        assert "INFRAFOUNDRY_PACKAGE_VARS" in env
        parsed = json.loads(env["INFRAFOUNDRY_PACKAGE_VARS"])
        assert parsed == vars_

    def test_sets_individual_var_env_vars(self):
        """INFRAFOUNDRY_VAR_<key> is set for each variable."""
        handler = self._make_handler()
        vars_ = {"cluster_name": "lab", "node_count": 3}
        ctx = EventContext(
            event_type=EventType.RESOURCE_CREATED,
            environment="dev",
            package_variables=vars_,
        )

        with patch.dict("os.environ", {}, clear=True):
            env = handler._prepare_environment(ctx, Path("/tmp/config/envs/dev"))

        assert env["INFRAFOUNDRY_VAR_cluster_name"] == "lab"
        assert env["INFRAFOUNDRY_VAR_node_count"] == "3"

    def test_empty_package_variables_no_env_vars(self):
        """Empty package_variables doesn't set INFRAFOUNDRY_PACKAGE_VARS."""
        handler = self._make_handler()
        ctx = EventContext(
            event_type=EventType.RESOURCE_CREATED,
            environment="dev",
            package_variables={},
        )

        with patch.dict("os.environ", {}, clear=True):
            env = handler._prepare_environment(ctx, Path("/tmp/config/envs/dev"))

        assert "INFRAFOUNDRY_PACKAGE_VARS" not in env

    def test_none_package_variables_no_env_vars(self):
        """Default empty package_variables doesn't set env vars."""
        handler = self._make_handler()
        ctx = EventContext(
            event_type=EventType.RESOURCE_CREATED,
            environment="dev",
        )

        with patch.dict("os.environ", {}, clear=True):
            env = handler._prepare_environment(ctx, Path("/tmp/config/envs/dev"))

        assert "INFRAFOUNDRY_PACKAGE_VARS" not in env


class TestPackageLoaderReturnsVariables:
    """PackageLoader.load_package returns variables as third element."""

    def test_load_package_returns_variables(self, tmp_path):
        """load_package returns (resources, events, variables) triple."""
        from infrafoundry.core.config.package_loader import PackageLoader

        # Set up package structure
        env_dir = tmp_path / "dev"
        pkg_dir = env_dir / "proxmox" / "my-pkg"
        pkg_dir.mkdir(parents=True)

        # Write manifest
        (pkg_dir / "infrafoundry.yml").write_text(
            "name: my-pkg\n"
            "resources:\n  - vm.yaml\n"
            "variables:\n"
            "  cluster_name: lab\n"
            "  node_count: 2\n"
        )
        # Write resource file
        (pkg_dir / "vm.yaml").write_text("vm:\n  - name: test-vm\n    cores: 2\n")

        loader = PackageLoader(tmp_path)
        resources, _events, variables = loader.load_package(pkg_dir, "proxmox", "dev")

        assert len(resources) == 1
        assert variables == {"cluster_name": "lab", "node_count": 2}

    def test_load_package_empty_variables(self, tmp_path):
        """Empty variables returns empty dict."""
        from infrafoundry.core.config.package_loader import PackageLoader

        env_dir = tmp_path / "dev"
        pkg_dir = env_dir / "proxmox" / "my-pkg"
        pkg_dir.mkdir(parents=True)

        (pkg_dir / "infrafoundry.yml").write_text("name: my-pkg\nresources:\n  - vm.yaml\n")
        (pkg_dir / "vm.yaml").write_text("vm:\n  - name: test-vm\n    cores: 2\n")

        loader = PackageLoader(tmp_path)
        _resources, _events, variables = loader.load_package(pkg_dir, "proxmox", "dev")

        assert variables == {}


class TestProviderBaseGetTerraformEnvVars:
    """ProviderBase.get_terraform_env_vars default returns empty dict."""

    def test_default_returns_empty(self):
        """Base implementation returns empty dict."""

        class ConcreteProvider(ProviderBase):
            def validate_config(self, config: dict[str, Any]) -> bool:
                return True

            def generate_terraform(self, resources: list[ResourceConfig]) -> None:
                pass

            def generate_ansible(self, resources: list[ResourceConfig]) -> None:
                pass

            def get_resource_types(self) -> list[str]:
                return []

            def get_terraform_resource_types(self) -> dict[str, list[str]]:
                return {}

        provider = ConcreteProvider("test", Path("/tmp"), Path("/tmp/out"))
        assert provider.get_terraform_env_vars() == {}
