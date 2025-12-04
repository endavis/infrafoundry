"""Unit tests for AnsibleRunner."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.runners.ansible_runner import AnsibleRunner


def _make_provider(tmp_path: Path) -> MagicMock:
    provider = MagicMock(spec=ProviderBase)
    provider.ansible_dir = tmp_path / "ansible"
    provider.ansible_dir.mkdir(parents=True)
    return provider


def test_is_available_checks_binary(tmp_path: Path) -> None:
    """Ansible availability uses ansible-playbook presence."""
    runner = AnsibleRunner()
    with patch("shutil.which", return_value="/usr/bin/ansible-playbook"):
        assert runner.is_available()
    with patch("shutil.which", return_value=None):
        assert not runner.is_available()


def test_initialize_handles_missing_binary(tmp_path: Path) -> None:
    """Initialize returns error when ansible is absent."""
    runner = AnsibleRunner()
    provider = _make_provider(tmp_path)
    with patch("shutil.which", return_value=None):
        result = runner.initialize(provider.ansible_dir)
    assert not result["success"]
    assert "not found" in result["error"]


def test_initialize_success(tmp_path: Path) -> None:
    """Initialize succeeds when ansible-playbook exists."""
    runner = AnsibleRunner()
    provider = _make_provider(tmp_path)
    with patch("shutil.which", return_value="/usr/bin/ansible-playbook"):
        result = runner.initialize(provider.ansible_dir)
    assert result["success"]


def test_plan_skips_when_no_playbook(tmp_path: Path) -> None:
    """Plan is skipped when playbook is missing."""
    runner = AnsibleRunner()
    provider = _make_provider(tmp_path)
    result = runner.plan(provider)
    assert result["success"]
    assert result.get("skipped") is True


def test_plan_runs_check_mode(tmp_path: Path) -> None:
    """Plan runs ansible-playbook with --check."""
    runner = AnsibleRunner()
    provider = _make_provider(tmp_path)
    (provider.ansible_dir / "playbook.yml").write_text("---")
    (provider.ansible_dir / "inventory.yml").write_text("---")

    with (
        patch("shutil.which", return_value="/usr/bin/ansible-playbook"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = SimpleNamespace(returncode=0)
        result = runner.plan(provider)

    assert result["success"]
    args = mock_run.call_args[0][0]
    assert "ansible-playbook" in args[0]
    assert "--check" in args


def test_apply_runs_without_check(tmp_path: Path) -> None:
    """Apply runs playbook without --check."""
    runner = AnsibleRunner()
    provider = _make_provider(tmp_path)
    (provider.ansible_dir / "playbook.yml").write_text("---")
    (provider.ansible_dir / "inventory.yml").write_text("---")

    with (
        patch("shutil.which", return_value="/usr/bin/ansible-playbook"),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = SimpleNamespace(returncode=0)
        result = runner.apply(provider)

    assert result["success"]
    args = mock_run.call_args[0][0]
    assert "--check" not in args


def test_validate_config_with_playbook(tmp_path: Path) -> None:
    """Validate config calls ansible-playbook --syntax-check."""
    runner = AnsibleRunner()
    provider = _make_provider(tmp_path)
    playbook = provider.ansible_dir / "playbook.yml"
    playbook.write_text("---")

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        result = runner.validate_config(provider)
    assert result["valid"]

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="bad")
        result = runner.validate_config(provider)
    assert not result["valid"]
    assert result["error"] == "bad"
