"""The host provider's generated ansible.cfg checks host keys (#1588)."""

from infrafoundry.providers.host import HostProvider

from .conftest import host


def test_ansible_cfg_checks_host_keys(provider: HostProvider) -> None:
    provider.generate_host([host()])

    cfg = (provider.ansible_dir / "ansible.cfg").read_text()

    assert "host_key_checking = True" in cfg
    assert "host_key_checking = False" not in cfg
