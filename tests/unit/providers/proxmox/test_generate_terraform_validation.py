"""Unit tests that the Proxmox provider wires its config validators into ``generate_terraform``.

Covers the wiring (not the validator logic — those are covered in
``test_storage_config_validator.py``, ``test_vm_config_validator.py``, and
``test_container_config_validator.py``). Verifies that ERROR-level findings raise
``SchemaValidationError`` before template rendering can silently drop a resource
(see issue #621), and that WARNING-level findings do not block generation.
"""

from __future__ import annotations

import pytest

from infrafoundry.core.exceptions import SchemaValidationError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.proxmox import ProxmoxProvider


@pytest.fixture
def provider(tmp_path):
    """Create a ProxmoxProvider with ``test`` as the active environment."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    p = ProxmoxProvider(config_dir, output_dir)
    p.set_environment("test")
    return p


def _storage(name: str, **config) -> ResourceConfig:
    """Build a Proxmox storage ResourceConfig for testing."""
    return ResourceConfig(
        name=name,
        type="storage",
        provider="proxmox",
        config={"name": name, **config},
    )


def _vm(name: str, **config) -> ResourceConfig:
    """Build a minimal Proxmox VM ResourceConfig for testing."""
    base: dict = {
        "name": name,
        "target_node": "pve1",
        "vmid": 200,
        "ssh_user": "ubuntu",
    }
    base.update(config)
    return ResourceConfig(name=name, type="vm", provider="proxmox", config=base)


def _container(name: str, **config) -> ResourceConfig:
    """Build a minimal Proxmox LXC container ResourceConfig for testing."""
    base: dict = {
        "name": name,
        "target_node": "pve1",
        "vmid": 300,
    }
    base.update(config)
    return ResourceConfig(name=name, type="container", provider="proxmox", config=base)


class TestStorageValidationWiring:
    """Wiring tests for StorageConfigValidator via ProxmoxProvider.generate_terraform."""

    def test_missing_backend_raises(self, provider):
        """A storage resource using ``type: nfs`` (not ``backend:``) raises.

        Reproduces the exact bug from issue #621 — schema mismatch on the
        ``backend`` key previously rendered an empty storage.tf silently.
        """
        storage = _storage(
            "nas01-infra",
            type="nfs",  # wrong key — should be ``backend``
            server="192.168.10.50",
            export="/export/infra",
        )
        with pytest.raises(SchemaValidationError) as exc_info:
            provider.generate_terraform([storage])
        message = str(exc_info.value)
        assert "nas01-infra" in message
        assert "backend" in message

    def test_invalid_content_types_raises(self, provider):
        """A storage resource with an unknown content type raises."""
        storage = _storage(
            "nas01-infra",
            backend="nfs",
            server="192.168.10.50",
            export="/export/infra",
            content_types=["bogus"],
        )
        with pytest.raises(SchemaValidationError) as exc_info:
            provider.generate_terraform([storage])
        message = str(exc_info.value)
        assert "nas01-infra" in message
        assert "bogus" in message


class TestVMValidationWiring:
    """Wiring tests for VMConfigValidator via ProxmoxProvider.generate_terraform."""

    def test_invalid_machine_type_raises(self, provider):
        """A VM with an unsupported ``machine`` value raises."""
        vm = _vm("web01", machine="invalid-machine")
        with pytest.raises(SchemaValidationError) as exc_info:
            provider.generate_terraform([vm])
        message = str(exc_info.value)
        assert "web01" in message
        assert "machine" in message

    def test_invalid_bios_raises(self, provider):
        """A VM with an unsupported ``bios`` value raises."""
        vm = _vm("web01", bios="award")
        with pytest.raises(SchemaValidationError) as exc_info:
            provider.generate_terraform([vm])
        message = str(exc_info.value)
        assert "web01" in message
        assert "bios" in message

    def test_negative_balloon_raises(self, provider):
        """A VM with a negative ``balloon`` value raises."""
        vm = _vm("web01", balloon=-1)
        with pytest.raises(SchemaValidationError) as exc_info:
            provider.generate_terraform([vm])
        message = str(exc_info.value)
        assert "web01" in message
        assert "balloon" in message


class TestContainerValidationWiring:
    """Wiring tests for ContainerConfigValidator via ProxmoxProvider.generate_terraform."""

    def test_missing_ostemplate_raises(self, provider):
        """A container without ``ostemplate`` (and no ``clone``) raises."""
        ct = _container("app01")  # no ostemplate, no clone
        with pytest.raises(SchemaValidationError) as exc_info:
            provider.generate_terraform([ct])
        message = str(exc_info.value)
        assert "app01" in message
        assert "ostemplate" in message

    def test_zero_cores_raises(self, provider):
        """A container with ``cores: 0`` raises."""
        ct = _container(
            "app01",
            ostemplate="local:vztmpl/alpine.tar.xz",
            cores=0,
        )
        with pytest.raises(SchemaValidationError) as exc_info:
            provider.generate_terraform([ct])
        message = str(exc_info.value)
        assert "app01" in message
        assert "cores" in message


class TestValidConfigPasses:
    """Wiring tests confirming valid configs do not raise."""

    def test_minimal_valid_storage_vm_container(self, provider):
        """A canonical valid mix of storage, VM, and container generates without raising."""
        storage = _storage(
            "nas01-infra",
            backend="nfs",
            server="192.168.10.50",
            export="/export/infra",
        )
        vm = _vm("web01")
        ct = _container(
            "app01",
            ostemplate="local:vztmpl/alpine.tar.xz",
        )
        # Should not raise.
        provider.generate_terraform([storage, vm, ct])


class TestErrorAggregation:
    """Wiring tests for multi-resource error collection."""

    def test_multiple_bad_resources_single_raise(self, provider):
        """Multiple invalid resources produce a single raise listing every failure."""
        resources = [
            _storage("bad-nfs", type="nfs", server="1.2.3.4", export="/e"),  # wrong key
            _storage(
                "bad-content",
                backend="dir",
                path="/mnt",
                content_types=["bogus"],
            ),
            _vm("bad-vm", machine="invalid-machine"),
            _container("bad-ct"),  # missing ostemplate
        ]
        with pytest.raises(SchemaValidationError) as exc_info:
            provider.generate_terraform(resources)
        message = str(exc_info.value)
        # Each failing resource name must appear in the aggregated message.
        assert "bad-nfs" in message
        assert "bad-content" in message
        assert "bad-vm" in message
        assert "bad-ct" in message


class TestWarningsDoNotBlock:
    """Wiring tests confirming WARNING-level findings do not raise."""

    def test_cifs_without_username_is_warning_only(self, provider):
        """CIFS storage without ``username`` emits a WARNING — generation must succeed."""
        storage = _storage(
            "backup-share",
            backend="cifs",
            server="192.168.10.50",
            share="backups",
            # username omitted intentionally — validator emits WARNING, not ERROR
        )
        # Should not raise, despite the validator reporting a warning.
        provider.generate_terraform([storage])
