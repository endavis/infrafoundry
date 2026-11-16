"""The enrollment playbook path is absolute, whatever the output dir is (#1416).

``ansible-playbook`` runs with ``cwd=ansible_dir``, so a path relative to the
caller's directory would not be found there.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.runners.host_runner import ANSIBLE_BINARY, AUTH_ENV_VAR, HostRunner
from infrafoundry.providers.host import HostProvider
from tests.unit.providers.host.conftest import SECRET_VALUE, host, make_env, tailscale_block

PATCH_RUN = "infrafoundry.core.runners.host_runner.subprocess.run"


@pytest.fixture
def relative_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> HostProvider:
    (tmp_path / "envs").mkdir()
    monkeypatch.chdir(tmp_path)
    p = HostProvider(Path("envs"), Path("generated"))
    p.set_environment("test")
    p.generate_host([host("a", tailscale=tailscale_block())])
    return p


def test_enrollment_playbook_is_absolute_for_a_relative_output_dir(
    relative_provider: HostProvider,
) -> None:
    (run,) = relative_provider.get_host_runs()

    assert run.enrollment_playbook is not None
    enrollment = Path(run.enrollment_playbook)
    assert enrollment.is_absolute()
    assert enrollment.exists()
    assert run.playbooks == (run.enrollment_playbook,)


def test_runner_passes_a_findable_playbook_and_injects_the_auth_env(
    relative_provider: HostProvider, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / ANSIBLE_BINARY
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    with (
        patch.object(
            HostProvider,
            "_load_environment_config",
            return_value=make_env({"tailscale": {"oauth_client_secret": SECRET_VALUE}}),
        ),
        patch(PATCH_RUN, return_value=MagicMock(returncode=0)) as run,
    ):
        result = HostRunner().apply(relative_provider)

    assert result["success"] is True
    argv = run.call_args.args[0]
    cwd = Path(run.call_args.kwargs["cwd"])
    assert (cwd / argv[-1]).exists()
    assert Path(argv[-1]).is_absolute()
    assert run.call_args.kwargs["env"][AUTH_ENV_VAR] == SECRET_VALUE
