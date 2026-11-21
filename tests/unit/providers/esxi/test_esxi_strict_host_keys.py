"""ESXi ssh connections check host keys against the operator's known_hosts (#1588)."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.types import EnvironmentData
from infrafoundry.providers.esxi import EsxiProvider
from infrafoundry.providers.esxi.exporter import EsxiConfigExporter


@pytest.fixture
def exporter() -> EsxiConfigExporter:
    env: EnvironmentData = {
        "provider_settings": {
            "esxi": {
                "hosts": {"esxi-01": {"hostname": "192.0.2.10", "username": "root"}},
                "timeout": 10,
            }
        }
    }
    return EsxiConfigExporter(env)


def test_ovf_template_ssh_opts_are_strict(tmp_path: Path) -> None:
    """All three ssh blocks (deploy, power on, destroy) use the strict option."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    provider = EsxiProvider(config_dir, output_dir)
    provider.set_environment("test")
    deployment = ResourceConfig(
        name="vm-01",
        type="ovf_deployment",
        provider="esxi",
        config={
            "host": "esxi-01",
            "ovf_source": "/path/to/example.ovf",
            "disk_store": "datastore1",
            "vm_name": "vm-01",
            "network_map": {"nat": "PG-Management"},
            "mac_map": {"ethernet0": "02:00:00:0A:01:01"},
        },
    )

    content = provider.render_template(
        "esxi/ovf_deployment.tf.j2",
        {"ovf_deployments": [deployment], "host_alias": EsxiProvider._host_alias},
    )

    expected = 'SSH_OPTS="-o StrictHostKeyChecking=yes -o ConnectTimeout=10"'
    assert content.count(expected) == 3
    assert "UserKnownHostsFile" not in content


@patch("subprocess.run")
def test_exporter_ssh_is_strict(mock_run: MagicMock, exporter: EsxiConfigExporter) -> None:
    mock_run.return_value = MagicMock(stdout="")

    exporter._ssh_command("192.0.2.10", "root", "test")

    argv = mock_run.call_args[0][0]
    assert "StrictHostKeyChecking=yes" in argv
    assert not any("UserKnownHostsFile" in arg for arg in argv)


@patch("subprocess.run")
def test_exporter_host_key_failure_logs_the_hint_and_reraises(
    mock_run: MagicMock, exporter: EsxiConfigExporter, caplog: pytest.LogCaptureFixture
) -> None:
    mock_run.side_effect = subprocess.CalledProcessError(
        255,
        "ssh",
        stderr="No ED25519 host key is known for 192.0.2.10 and you have requested strict "
        "checking.\nHost key verification failed.\n",
    )

    with caplog.at_level("ERROR"), pytest.raises(subprocess.CalledProcessError):
        exporter._ssh_command("192.0.2.10", "root", "test")

    assert "ssh-keyscan -t ed25519 192.0.2.10" in caplog.text
