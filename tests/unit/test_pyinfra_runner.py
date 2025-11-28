"""Tests for pyinfra runner and integration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners import PyInfraRunner


@pytest.fixture
def runner() -> PyInfraRunner:
    """Create a PyInfraRunner instance."""
    return PyInfraRunner()


@pytest.fixture
def mock_provider(tmp_path: Path) -> MagicMock:
    """Create a mock provider with pyinfra support."""
    provider = MagicMock(spec=ProviderBase)
    provider.pyinfra_dir = tmp_path / "pyinfra"
    provider.pyinfra_dir.mkdir(parents=True)
    return provider


def test_tool_name(runner: PyInfraRunner) -> None:
    """Test tool name property."""
    assert runner.tool_name == "pyinfra"


def test_is_available_mock(runner: PyInfraRunner) -> None:
    """Test availability check with mock."""
    with patch("shutil.which") as mock_which:
        mock_which.return_value = "/usr/bin/pyinfra"
        assert runner.is_available()

        mock_which.return_value = None
        assert not runner.is_available()


def test_validate_config_missing_dir(runner: PyInfraRunner) -> None:
    """Test validation when pyinfra_dir is missing."""
    provider = MagicMock(spec=ProviderBase)
    del provider.pyinfra_dir  # Ensure attribute is missing
    # getattr will return None if not found
    # We need to simulate the object not having the attribute or it being None
    # MagicMock usually creates attributes on access, so we set a side effect or specific value
    # But for getattr(obj, "attr", None), we need to ensure it returns None
    # Let's just use a plain class/object for this test or configure the mock

    class NoPyInfraProvider:
        pass

    result = runner.validate_config(NoPyInfraProvider())  # type: ignore
    assert not result["valid"]
    assert "Provider does not support pyinfra" in result["error"]


def test_validate_config_missing_files(runner: PyInfraRunner, mock_provider: MagicMock) -> None:
    """Test validation with missing files."""
    result = runner.validate_config(mock_provider)
    assert result[
        "valid"
    ]  # It returns valid but with message "No deploy.py found" if deploy.py is missing

    # Add inventory but no deploy
    (mock_provider.pyinfra_dir / "inventory.py").touch()
    result = runner.validate_config(mock_provider)
    assert result["valid"]
    assert "No deploy.py found" in result["message"]

    # Add deploy but no inventory
    (mock_provider.pyinfra_dir / "inventory.py").unlink()
    (mock_provider.pyinfra_dir / "deploy.py").touch()
    result = runner.validate_config(mock_provider)
    assert not result["valid"]
    assert "inventory.py missing" in result["error"]


def test_validate_config_valid(runner: PyInfraRunner, mock_provider: MagicMock) -> None:
    """Test validation with valid files."""
    (mock_provider.pyinfra_dir / "inventory.py").write_text("production = []")
    (mock_provider.pyinfra_dir / "deploy.py").write_text("print('hello')")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        result = runner.validate_config(mock_provider)
        assert result["valid"]


def test_run_plan(runner: PyInfraRunner, mock_provider: MagicMock) -> None:
    """Test plan execution."""
    (mock_provider.pyinfra_dir / "inventory.py").touch()
    (mock_provider.pyinfra_dir / "deploy.py").touch()

    with patch("shutil.which", return_value="/bin/pyinfra"), patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0

        result = runner.run(mock_provider, "plan")

        assert result["success"]
        args = mock_run.call_args[0][0]
        assert args[0] == "pyinfra"
        assert "--dry" in args
        assert str(mock_provider.pyinfra_dir / "inventory.py") in args
        assert str(mock_provider.pyinfra_dir / "deploy.py") in args


def test_run_apply(runner: PyInfraRunner, mock_provider: MagicMock) -> None:
    """Test apply execution."""
    (mock_provider.pyinfra_dir / "inventory.py").touch()
    (mock_provider.pyinfra_dir / "deploy.py").touch()

    with patch("shutil.which", return_value="/bin/pyinfra"), patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0

        result = runner.run(mock_provider, "apply")

        assert result["success"]
        args = mock_run.call_args[0][0]
        assert args[0] == "pyinfra"
        assert "--yes" in args
        assert "--dry" not in args
