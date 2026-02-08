"""Unit tests for IaCTool enum and EnvironmentConfig.iac_tool field."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from infrafoundry.core.config.models import EnvironmentConfig, IaCTool


class TestIaCToolEnum:
    """Tests for the IaCTool enum."""

    def test_terraform_value(self) -> None:
        """TERRAFORM enum has correct string value."""
        assert IaCTool.TERRAFORM.value == "terraform"

    def test_opentofu_value(self) -> None:
        """OPENTOFU enum has correct string value."""
        assert IaCTool.OPENTOFU.value == "opentofu"

    def test_is_string_enum(self) -> None:
        """IaCTool members are usable as strings."""
        assert IaCTool.TERRAFORM == "terraform"
        assert IaCTool.OPENTOFU == "opentofu"

    def test_from_string(self) -> None:
        """IaCTool can be constructed from string values."""
        assert IaCTool("terraform") is IaCTool.TERRAFORM
        assert IaCTool("opentofu") is IaCTool.OPENTOFU

    def test_invalid_value_raises(self) -> None:
        """Invalid string raises ValueError."""
        with pytest.raises(ValueError):
            IaCTool("invalid")


class TestEnvironmentConfigIaCTool:
    """Tests for iac_tool field on EnvironmentConfig."""

    def test_default_is_terraform(self) -> None:
        """iac_tool defaults to terraform for backward compatibility."""
        config = EnvironmentConfig(name="dev")
        assert config.iac_tool == IaCTool.TERRAFORM

    def test_explicit_terraform(self) -> None:
        """Explicit terraform value works."""
        config = EnvironmentConfig(name="dev", iac_tool="terraform")
        assert config.iac_tool == IaCTool.TERRAFORM

    def test_explicit_opentofu(self) -> None:
        """Setting opentofu works."""
        config = EnvironmentConfig(name="dev", iac_tool="opentofu")
        assert config.iac_tool == IaCTool.OPENTOFU

    def test_invalid_tool_raises(self) -> None:
        """Invalid iac_tool value raises validation error."""
        with pytest.raises(ValueError):
            EnvironmentConfig(name="dev", iac_tool="pulumi")  # type: ignore[arg-type]

    def test_from_yaml_dict(self) -> None:
        """Config can be constructed from dict (simulating YAML load)."""
        data = {"name": "staging", "iac_tool": "opentofu"}
        config = EnvironmentConfig(**data)
        assert config.iac_tool == IaCTool.OPENTOFU

    def test_from_yaml_dict_without_iac_tool(self) -> None:
        """Config without iac_tool field uses default."""
        data = {"name": "prod"}
        config = EnvironmentConfig(**data)
        assert config.iac_tool == IaCTool.TERRAFORM


class TestIaCToolEnvVarOverride:
    """Tests for INFRAFOUNDRY_IAC_TOOL environment variable override."""

    def _write_settings(self, tmp_path: Path, env_name: str, data: dict) -> None:
        """Write a settings.yaml for the given environment."""
        env_dir = tmp_path / env_name
        env_dir.mkdir(parents=True, exist_ok=True)
        with open(env_dir / "settings.yaml", "w") as f:
            yaml.dump(data, f)

    def test_env_var_overrides_yaml(self, tmp_path: Path) -> None:
        """INFRAFOUNDRY_IAC_TOOL overrides settings.yaml value."""
        from infrafoundry.core.config.config_manager import ConfigManager

        self._write_settings(tmp_path, "dev", {"name": "dev", "iac_tool": "terraform"})

        with patch.dict("os.environ", {"INFRAFOUNDRY_IAC_TOOL": "opentofu"}):
            cm = ConfigManager(base_dir=tmp_path)
            config = cm.load_environment("dev")

        assert config.iac_tool == IaCTool.OPENTOFU

    def test_env_var_sets_when_yaml_has_no_iac_tool(self, tmp_path: Path) -> None:
        """INFRAFOUNDRY_IAC_TOOL sets iac_tool when not in YAML."""
        from infrafoundry.core.config.config_manager import ConfigManager

        self._write_settings(tmp_path, "dev", {"name": "dev"})

        with patch.dict("os.environ", {"INFRAFOUNDRY_IAC_TOOL": "opentofu"}):
            cm = ConfigManager(base_dir=tmp_path)
            config = cm.load_environment("dev")

        assert config.iac_tool == IaCTool.OPENTOFU

    def test_invalid_env_var_is_ignored(self, tmp_path: Path) -> None:
        """Invalid INFRAFOUNDRY_IAC_TOOL value is ignored, YAML value used."""
        from infrafoundry.core.config.config_manager import ConfigManager

        self._write_settings(tmp_path, "dev", {"name": "dev", "iac_tool": "opentofu"})

        with patch.dict("os.environ", {"INFRAFOUNDRY_IAC_TOOL": "invalid"}):
            cm = ConfigManager(base_dir=tmp_path)
            config = cm.load_environment("dev")

        assert config.iac_tool == IaCTool.OPENTOFU

    def test_no_env_var_uses_yaml(self, tmp_path: Path) -> None:
        """Without env var, YAML value is used as-is."""
        from infrafoundry.core.config.config_manager import ConfigManager

        self._write_settings(tmp_path, "dev", {"name": "dev", "iac_tool": "opentofu"})

        with patch.dict("os.environ", {}, clear=False):
            # Ensure the env var is not set
            import os

            os.environ.pop("INFRAFOUNDRY_IAC_TOOL", None)
            cm = ConfigManager(base_dir=tmp_path)
            config = cm.load_environment("dev")

        assert config.iac_tool == IaCTool.OPENTOFU
