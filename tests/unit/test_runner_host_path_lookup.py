"""HostRunner resolves ``ansible-playbook`` from PATH, not its registry name (#1413).

Unlike ``test_runner_host.py`` these tests do not patch ``shutil.which`` or
``tool_path``; only ``subprocess.run`` is patched, so the real lookup runs.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.runners.host_runner import ANSIBLE_BINARY, HostRunner
from infrafoundry.providers.host import HostProvider
from tests.unit.providers.host.conftest import host

PATCH_RUN = "infrafoundry.core.runners.host_runner.subprocess.run"


@pytest.fixture
def provider(tmp_path: Path) -> HostProvider:
    (tmp_path / "envs").mkdir()
    (tmp_path / "playbooks").mkdir()
    (tmp_path / "playbooks" / "base.yml").write_text("---\n")
    p = HostProvider(tmp_path / "envs", tmp_path / "output")
    p.set_environment("test")
    p.generate_host([host("a", ansible={"playbooks": ["playbooks/base.yml"]})])
    return p


def test_apply_runs_the_ansible_playbook_binary_found_on_path(
    provider: HostProvider, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / ANSIBLE_BINARY
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    with patch(PATCH_RUN, return_value=MagicMock(returncode=0)) as run:
        result = HostRunner().apply(provider)

    assert result["success"] is True
    assert run.call_args.args[0][0] == str(stub)


def test_apply_reports_a_clear_error_when_ansible_playbook_is_missing(
    provider: HostProvider, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))

    with patch(PATCH_RUN) as run:
        result = HostRunner().apply(provider)

    run.assert_not_called()
    assert result["success"] is False
    assert "ansible-playbook not found" in result["error"]


def test_tool_path_error_names_ansible_playbook_not_the_registry_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    runner = HostRunner()

    with pytest.raises(FileNotFoundError, match="ansible-playbook not found"):
        _ = runner.tool_path
    assert runner.is_available() is False
    assert runner.tool_name == "host_ansible"
