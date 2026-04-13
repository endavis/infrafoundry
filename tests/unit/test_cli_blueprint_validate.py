"""Unit tests for the 'blueprint validate' CLI command."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main
from infrafoundry.core.config.blueprint_validator import (
    BlueprintValidationResult,
    ProviderValidationResult,
)


@pytest.fixture
def cli_runner():
    """Fixture for invoking CLI commands."""
    return CliRunner()


def _clean_result(name: str = "test-bp") -> BlueprintValidationResult:
    """Build a clean validation result."""
    return BlueprintValidationResult(
        blueprint_name=name,
        is_multi_provider=False,
        providers=[
            ProviderValidationResult(
                provider="default",
                template_vars=frozenset({"vm_name", "cores"}),
                defaults=frozenset({"vm_name", "cores"}),
            )
        ],
    )


def _error_result(name: str = "test-bp") -> BlueprintValidationResult:
    """Build a validation result with errors."""
    return BlueprintValidationResult(
        blueprint_name=name,
        is_multi_provider=False,
        providers=[
            ProviderValidationResult(
                provider="default",
                template_vars=frozenset({"vm_name", "missing_var"}),
                defaults=frozenset({"vm_name"}),
                errors=["Undefined variable: 'missing_var' (not in any defaults layer)"],
            )
        ],
    )


def _warning_result(name: str = "test-bp") -> BlueprintValidationResult:
    """Build a validation result with warnings only."""
    return BlueprintValidationResult(
        blueprint_name=name,
        is_multi_provider=True,
        providers=[
            ProviderValidationResult(
                provider="a",
                template_vars=frozenset({"cluster_name", "shared"}),
                defaults=frozenset({"cluster_name", "shared"}),
            ),
            ProviderValidationResult(
                provider="b",
                template_vars=frozenset({"cluster_name"}),
                defaults=frozenset({"cluster_name", "shared"}),
                warnings=[
                    "Asymmetric variable: 'shared' is in global defaults and used by a but not b"
                ],
            ),
        ],
    )


def _mock_validator(result: BlueprintValidationResult) -> MagicMock:
    """Build a mock BlueprintValidator that returns the given result."""
    mock = MagicMock()
    mock.validate.return_value = result
    return mock


@pytest.mark.unit
class TestBlueprintValidateHelp:
    """Tests for blueprint validate --help."""

    def test_help(self, cli_runner):
        """--help exits 0 and shows usage."""
        result = cli_runner.invoke(main, ["blueprint", "validate", "--help"])
        assert result.exit_code == 0
        assert "Validate blueprint templates" in result.output


@pytest.mark.unit
class TestBlueprintValidateClean:
    """Tests for clean validation results."""

    @patch("infrafoundry.cli.commands.blueprint.validate.BlueprintValidator")
    @patch("infrafoundry.cli.commands.blueprint.validate.BlueprintResolver")
    def test_clean_exit_zero(self, mock_resolver_cls, mock_validator_cls, cli_runner):
        """Clean result exits with code 0."""
        mock_resolver = mock_resolver_cls.return_value
        mock_resolver.resolve.return_value = {"name": "test-bp", "blueprint_dir": Path(".")}
        mock_validator_cls.return_value = _mock_validator(_clean_result())

        result = cli_runner.invoke(main, ["blueprint", "validate", "-b", "test-bp"])
        assert result.exit_code == 0
        assert "OK" in result.output


@pytest.mark.unit
class TestBlueprintValidateErrors:
    """Tests for validation errors."""

    @patch("infrafoundry.cli.commands.blueprint.validate.BlueprintValidator")
    @patch("infrafoundry.cli.commands.blueprint.validate.BlueprintResolver")
    def test_errors_exit_one(self, mock_resolver_cls, mock_validator_cls, cli_runner):
        """Errors in validation result in exit code 1."""
        mock_resolver = mock_resolver_cls.return_value
        mock_resolver.resolve.return_value = {"name": "test-bp", "blueprint_dir": Path(".")}
        mock_validator_cls.return_value = _mock_validator(_error_result())

        result = cli_runner.invoke(main, ["blueprint", "validate", "-b", "test-bp"])
        assert result.exit_code == 1
        assert "FAIL" in result.output
        assert "missing_var" in result.output


@pytest.mark.unit
class TestBlueprintValidateWarnings:
    """Tests for warnings-only results."""

    @patch("infrafoundry.cli.commands.blueprint.validate.BlueprintValidator")
    @patch("infrafoundry.cli.commands.blueprint.validate.BlueprintResolver")
    def test_warnings_exit_zero(self, mock_resolver_cls, mock_validator_cls, cli_runner):
        """Warnings-only result exits with code 0."""
        mock_resolver = mock_resolver_cls.return_value
        mock_resolver.resolve.return_value = {"name": "test-bp", "blueprint_dir": Path(".")}
        mock_validator_cls.return_value = _mock_validator(_warning_result())

        result = cli_runner.invoke(main, ["blueprint", "validate", "-b", "test-bp"])
        assert result.exit_code == 0
        assert "WARN" in result.output


@pytest.mark.unit
class TestBlueprintValidateAll:
    """Tests for --all flag."""

    @patch("infrafoundry.cli.commands.blueprint.validate.BlueprintValidator")
    @patch("infrafoundry.cli.commands.blueprint.validate.BlueprintResolver")
    def test_all_flag_validates_all(self, mock_resolver_cls, mock_validator_cls, cli_runner):
        """--all validates every blueprint returned by list_blueprints."""
        mock_resolver = mock_resolver_cls.return_value
        mock_resolver.list_blueprints.return_value = ["aiqum", "k3s-cluster"]
        mock_resolver.resolve.side_effect = [
            {"name": "aiqum", "blueprint_dir": Path(".")},
            {"name": "k3s-cluster", "blueprint_dir": Path(".")},
        ]
        mock_v1 = _mock_validator(_clean_result("aiqum"))
        mock_v2 = _mock_validator(_clean_result("k3s-cluster"))
        mock_validator_cls.side_effect = [mock_v1, mock_v2]

        result = cli_runner.invoke(main, ["blueprint", "validate", "--all"])
        assert result.exit_code == 0
        assert "aiqum" in result.output
        assert "k3s-cluster" in result.output


@pytest.mark.unit
class TestBlueprintValidateUnknown:
    """Tests for unknown blueprint name."""

    @patch("infrafoundry.cli.commands.blueprint.validate.BlueprintResolver")
    def test_unknown_blueprint_exit_one(self, mock_resolver_cls, cli_runner):
        """Unknown blueprint name produces error and exit code 1."""
        from infrafoundry.core.exceptions import InvalidConfigurationError

        mock_resolver = mock_resolver_cls.return_value
        mock_resolver.resolve.side_effect = InvalidConfigurationError("Blueprint 'nope' not found")

        result = cli_runner.invoke(main, ["blueprint", "validate", "-b", "nope"])
        assert result.exit_code != 0
        assert "nope" in result.output


@pytest.mark.unit
class TestBlueprintValidateJsonFormat:
    """Tests for --format json output."""

    @patch("infrafoundry.cli.commands.blueprint.validate.BlueprintValidator")
    @patch("infrafoundry.cli.commands.blueprint.validate.BlueprintResolver")
    def test_json_output(self, mock_resolver_cls, mock_validator_cls, cli_runner):
        """--format json produces valid JSON."""
        mock_resolver = mock_resolver_cls.return_value
        mock_resolver.resolve.return_value = {"name": "test-bp", "blueprint_dir": Path(".")}
        mock_validator_cls.return_value = _mock_validator(_clean_result())

        result = cli_runner.invoke(
            main, ["blueprint", "validate", "-b", "test-bp", "--format", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["blueprint_name"] == "test-bp"
        assert data["has_errors"] is False
        assert "providers" in data


@pytest.mark.unit
class TestBlueprintValidateNoArgs:
    """Tests for missing required arguments."""

    def test_no_args_shows_error(self, cli_runner):
        """Invoking without --blueprint or --all shows usage error."""
        result = cli_runner.invoke(main, ["blueprint", "validate"])
        assert result.exit_code != 0
        assert "Specify" in result.output or "Error" in result.output
