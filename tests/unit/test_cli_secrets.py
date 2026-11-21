"""Unit tests for the 'secrets' CLI command group."""

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from infrafoundry.cli.main import main


@pytest.fixture
def cli_runner() -> CliRunner:
    """Fixture for invoking CLI commands."""
    return CliRunner()


def test_secrets_init_basic(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Test secrets init command."""
    key_file = tmp_path / "age.key"

    # Mock subprocess.run for age-keygen
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stderr = "# public key: age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    with (
        patch("subprocess.run", return_value=mock_result),
        patch("infrafoundry.cli.commands.secrets.secrets.create_sops_config"),
    ):
        result = cli_runner.invoke(main, ["secrets", "init", "--key-file", str(key_file)])

        assert result.exit_code == 0
        assert "Created age key:" in result.output
        assert "Created .sops.yaml" in result.output


def test_secrets_init_key_exists(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Test secrets init when key file already exists."""
    key_file = tmp_path / "age.key"
    key_file.touch()

    result = cli_runner.invoke(main, ["secrets", "init", "--key-file", str(key_file)])

    assert result.exit_code == 0
    assert "Key file already exists" in result.output


def test_secrets_init_age_keygen_failure(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Test secrets init when age-keygen fails."""
    key_file = tmp_path / "age.key"

    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = "age-keygen: command not found"

    with patch("subprocess.run", return_value=mock_result):
        result = cli_runner.invoke(main, ["secrets", "init", "--key-file", str(key_file)])

        assert result.exit_code != 0
        assert "Failed to generate key" in result.output


def test_secrets_encrypt_basic(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Test secrets encrypt command."""
    test_file = tmp_path / "test.yaml"
    test_file.write_text("secret: value")

    # Mock subprocess.run for sops
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        result = cli_runner.invoke(main, ["secrets", "encrypt", str(test_file)])

        assert result.exit_code == 0
        assert "Encrypted:" in result.output


def test_secrets_encrypt_file_not_found(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Test secrets encrypt when file doesn't exist."""
    nonexistent_file = tmp_path / "nonexistent.yaml"

    result = cli_runner.invoke(main, ["secrets", "encrypt", str(nonexistent_file)])

    assert result.exit_code != 0
    assert "File not found" in result.output


def test_secrets_encrypt_sops_failure(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Test secrets encrypt when sops fails."""
    test_file = tmp_path / "test.yaml"
    test_file.write_text("secret: value")

    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = "sops: error: no key found"

    with patch("subprocess.run", return_value=mock_result):
        result = cli_runner.invoke(main, ["secrets", "encrypt", str(test_file)])

        assert result.exit_code != 0
        assert "Encryption failed" in result.output


def test_secrets_decrypt_basic(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Test secrets decrypt command."""
    test_file = tmp_path / "test.yaml"
    test_file.write_text("encrypted content")

    # Mock subprocess.run for sops
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "secret: value\n"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        result = cli_runner.invoke(main, ["secrets", "decrypt", str(test_file)])

        assert result.exit_code == 0
        assert "secret: value" in result.output


def test_secrets_decrypt_file_not_found(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Test secrets decrypt when file doesn't exist."""
    nonexistent_file = tmp_path / "nonexistent.yaml"

    result = cli_runner.invoke(main, ["secrets", "decrypt", str(nonexistent_file)])

    assert result.exit_code != 0
    assert "File not found" in result.output


def test_secrets_decrypt_sops_failure(cli_runner: CliRunner, tmp_path: Path) -> None:
    """Test secrets decrypt when sops fails."""
    test_file = tmp_path / "test.yaml"
    test_file.write_text("encrypted content")

    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = "sops: error: failed to decrypt"

    with patch("subprocess.run", return_value=mock_result):
        result = cli_runner.invoke(main, ["secrets", "decrypt", str(test_file)])

        assert result.exit_code != 0
        assert "Decryption failed" in result.output


# --- secrets host-keys (#1581) ---

_HK_PUBLIC = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleSentinelPublicKey0"
_HK_PRIVATE = "-----BEGIN OPENSSH " + "PRIVATE KEY-----\nSENTINEL-NOT-A-REAL-KEY\n"
_STORE = "infrafoundry.cli.commands.secrets.secrets.host_key_store"


def _hk_vm(name: str, secrets: dict[str, Any] | None = None) -> Any:
    from infrafoundry.core.provider import ResourceConfig

    return ResourceConfig(
        name=name,
        type="vm",
        provider="proxmox",
        config={"ssh_host_key": {"address": "192.0.2.10"}},
        package_name="demo",
        package_path="proxmox/demo",
        package_variables={"jumphost": "ansible@jump.example"},
        package_secrets=secrets,
    )


def _hk_orchestrator(tmp_path: Path, resources: list[Any], deployed: set[str]) -> Mock:
    from types import SimpleNamespace

    from infrafoundry.core.state.models import ResourceState

    records = [
        SimpleNamespace(
            provider="proxmox",
            name=name,
            state=ResourceState.ACTIVE,
            created_at=1,
        )
        for name in deployed
    ]
    orchestrator = Mock()
    orchestrator.config_manager.get_all_resources_all_providers.return_value = resources
    orchestrator.config_manager.base_dir = tmp_path / "envs"
    orchestrator.state_manager.get_resources.return_value = records
    return orchestrator


def _invoke_host_keys(
    cli_runner: CliRunner, orchestrator: Mock, *args: str
) -> tuple[Any, dict[str, Mock]]:
    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=orchestrator),
        patch("infrafoundry.cli.main._load_env_credentials"),
        patch(f"{_STORE}.generate_keypair", return_value=(_HK_PRIVATE, _HK_PUBLIC)) as gen,
        patch(f"{_STORE}.scan_public_key", return_value=_HK_PUBLIC) as scan,
        patch(f"{_STORE}.fingerprint", return_value="SHA256:abc") as fp,
        patch(f"{_STORE}.write_entry") as write,
        patch(f"{_STORE}.ensure_secrets_file", return_value=False) as ensure,
    ):
        result = cli_runner.invoke(main, ["secrets", "host-keys", "--env", "dev", *args])
    store = {"gen": gen, "scan": scan, "fp": fp, "write": write, "ensure": ensure}
    return result, store


def test_host_keys_generates_for_an_undeployed_vm(cli_runner: CliRunner, tmp_path: Path) -> None:
    orchestrator = _hk_orchestrator(tmp_path, [_hk_vm("vm-01", {})], deployed=set())

    result, mocks = _invoke_host_keys(cli_runner, orchestrator)

    assert result.exit_code == 0, result.output
    assert "generated SHA256:abc" in result.output
    assert "SENTINEL" not in result.output
    write = mocks["write"]
    path, name, entry = write.call_args.args[:3]
    assert path == tmp_path / "envs" / "dev" / "proxmox/demo" / "secrets.yaml"
    assert name == "vm-01"
    assert entry == {"ed25519_private": _HK_PRIVATE, "ed25519_public": _HK_PUBLIC}
    mocks["scan"].assert_not_called()
    # sops finds .sops.yaml from its cwd, so the config repo root is passed.
    mocks["ensure"].assert_called_once_with(path, tmp_path)


def test_host_keys_pins_a_deployed_vm_from_the_jumphost(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    orchestrator = _hk_orchestrator(tmp_path, [_hk_vm("vm-01", {})], deployed={"vm-01"})

    result, mocks = _invoke_host_keys(cli_runner, orchestrator)

    assert result.exit_code == 0, result.output
    assert "pinned    SHA256:abc" in result.output
    mocks["scan"].assert_called_once_with("192.0.2.10", "ansible@jump.example")
    assert mocks["write"].call_args.args[2] == {"ed25519_public": _HK_PUBLIC}
    mocks["gen"].assert_not_called()


def test_host_keys_skips_recorded_vms(cli_runner: CliRunner, tmp_path: Path) -> None:
    secrets = {"ssh_host_keys": {"vm-01": {"ed25519_public": _HK_PUBLIC}}}
    orchestrator = _hk_orchestrator(tmp_path, [_hk_vm("vm-01", secrets)], deployed={"vm-01"})

    result, mocks = _invoke_host_keys(cli_runner, orchestrator)

    assert result.exit_code == 0
    assert "skipped" in result.output
    mocks["write"].assert_not_called()


def test_host_keys_dry_run_writes_nothing(cli_runner: CliRunner, tmp_path: Path) -> None:
    orchestrator = _hk_orchestrator(
        tmp_path, [_hk_vm("vm-01", {}), _hk_vm("vm-02", {})], deployed={"vm-02"}
    )

    result, mocks = _invoke_host_keys(cli_runner, orchestrator, "--dry-run")

    assert result.exit_code == 0
    assert "would generate" in result.output
    assert "would pin" in result.output
    for name in ("write", "gen", "scan", "ensure"):
        mocks[name].assert_not_called()


def test_host_keys_refuses_regenerate_of_a_deployed_vm(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    secrets = {"ssh_host_keys": {"vm-01": {"ed25519_public": _HK_PUBLIC}}}
    orchestrator = _hk_orchestrator(tmp_path, [_hk_vm("vm-01", secrets)], deployed={"vm-01"})

    result, mocks = _invoke_host_keys(cli_runner, orchestrator, "--regenerate", "vm-01")

    assert result.exit_code != 0
    assert "refused" in result.output
    mocks["write"].assert_not_called()


def test_host_keys_unknown_regenerate_name_is_an_error(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    orchestrator = _hk_orchestrator(tmp_path, [_hk_vm("vm-01", {})], deployed=set())

    result, _ = _invoke_host_keys(cli_runner, orchestrator, "--regenerate", "nope")

    assert result.exit_code != 0
    assert "nope" in result.output


def test_host_keys_error_exits_non_zero_without_the_key(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    from infrafoundry.core.exceptions import SecretError

    orchestrator = _hk_orchestrator(tmp_path, [_hk_vm("vm-01", {})], deployed=set())
    with (
        patch("infrafoundry.cli.main._get_orchestrator", return_value=orchestrator),
        patch("infrafoundry.cli.main._load_env_credentials"),
        patch(f"{_STORE}.generate_keypair", return_value=(_HK_PRIVATE, _HK_PUBLIC)),
        patch(f"{_STORE}.ensure_secrets_file", return_value=False),
        patch(f"{_STORE}.write_entry", side_effect=SecretError("sops failed (exit 1)")),
    ):
        result = cli_runner.invoke(main, ["secrets", "host-keys", "--env", "dev"])

    assert result.exit_code != 0
    assert "failed" in result.output
    assert "SENTINEL" not in result.output


def test_host_keys_limits_to_a_package(cli_runner: CliRunner, tmp_path: Path) -> None:
    orchestrator = _hk_orchestrator(tmp_path, [_hk_vm("vm-01", {})], deployed=set())

    result, mocks = _invoke_host_keys(cli_runner, orchestrator, "--package", "other/pkg")

    assert result.exit_code == 0
    assert "nothing to do" in result.output
    mocks["write"].assert_not_called()
