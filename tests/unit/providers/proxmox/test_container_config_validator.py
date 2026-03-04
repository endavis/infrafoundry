"""Unit tests for Proxmox ContainerConfigValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.proxmox.validators.container_config_validator import (
    ContainerConfigValidator,
)


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create a ContainerConfigValidator instance."""
    return ContainerConfigValidator(report)


def _ct(name: str = "test-ct", **config) -> ResourceConfig:
    """Helper to create a container ResourceConfig."""
    return ResourceConfig(
        name=name,
        type="container",
        provider="proxmox",
        config={"name": name, "target_node": "pve01", **config},
    )


class TestOSTemplateValidation:
    """Tests for ostemplate validation."""

    def test_valid_ostemplate(self, validator, report):
        """Valid ostemplate should not trigger an error."""
        validator.validate(
            [_ct(ostemplate="nas01:vztmpl/alpine-3.21-default_20250108_amd64.tar.xz")]
        )
        report.add_check.assert_not_called()

    def test_valid_ostemplate_zst(self, validator, report):
        """Zstandard-compressed ostemplate should be valid."""
        validator.validate(
            [_ct(ostemplate="local:vztmpl/ubuntu-24.04-standard_24.04-2_amd64.tar.zst")]
        )
        report.add_check.assert_not_called()

    def test_invalid_ostemplate_format(self, validator, report):
        """Invalid ostemplate format should trigger an error."""
        validator.validate([_ct(ostemplate="/path/to/template.tar.xz")])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert call_args["level"] == ValidationLevel.ERROR
        assert "ostemplate" in call_args["message"]

    def test_missing_ostemplate_no_clone(self, validator, report):
        """Missing ostemplate without clone should trigger an error."""
        validator.validate([_ct()])
        calls = [
            c[1]
            for c in report.add_check.call_args_list
            if "ostemplate" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is False
        assert calls[0]["level"] == ValidationLevel.ERROR

    def test_missing_ostemplate_with_clone(self, validator, report):
        """Missing ostemplate with clone should not trigger ostemplate error."""
        validator.validate([_ct(clone={"vm_id": 100})])
        ostemplate_calls = [
            c[1]
            for c in report.add_check.call_args_list
            if "ostemplate" in c[1].get("check_name", "")
        ]
        assert len(ostemplate_calls) == 0


class TestOSTypeValidation:
    """Tests for ostype validation."""

    def test_known_ostype_no_warning(self, validator, report):
        """Known ostype should not trigger a warning."""
        for ostype in ("alpine", "debian", "ubuntu", "centos"):
            report.reset_mock()
            validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", ostype=ostype)])
            ostype_calls = [
                c[1]
                for c in report.add_check.call_args_list
                if "ostype" in c[1].get("check_name", "")
            ]
            assert len(ostype_calls) == 0

    def test_unknown_ostype_warning(self, validator, report):
        """Unknown ostype should trigger a warning."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", ostype="freebsd")])
        calls = [
            c[1] for c in report.add_check.call_args_list if "ostype" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is True
        assert calls[0]["level"] == ValidationLevel.WARNING

    def test_no_ostype_no_check(self, validator, report):
        """No ostype should not trigger any check."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz")])
        ostype_calls = [
            c[1] for c in report.add_check.call_args_list if "ostype" in c[1].get("check_name", "")
        ]
        assert len(ostype_calls) == 0


class TestRootfsValidation:
    """Tests for rootfs.size validation."""

    def test_valid_rootfs_size(self, validator, report):
        """Valid rootfs size should not trigger an error."""
        validator.validate(
            [_ct(ostemplate="s:vztmpl/t.tar.xz", rootfs={"storage": "local", "size": 8})]
        )
        rootfs_calls = [
            c[1] for c in report.add_check.call_args_list if "rootfs" in c[1].get("check_name", "")
        ]
        assert len(rootfs_calls) == 0

    def test_invalid_rootfs_size_zero(self, validator, report):
        """Rootfs size of 0 should trigger an error."""
        validator.validate(
            [_ct(ostemplate="s:vztmpl/t.tar.xz", rootfs={"storage": "local", "size": 0})]
        )
        report.add_check.assert_called()
        calls = [
            c[1] for c in report.add_check.call_args_list if "rootfs" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is False

    def test_invalid_rootfs_size_negative(self, validator, report):
        """Negative rootfs size should trigger an error."""
        validator.validate(
            [_ct(ostemplate="s:vztmpl/t.tar.xz", rootfs={"storage": "local", "size": -1})]
        )
        calls = [
            c[1] for c in report.add_check.call_args_list if "rootfs" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is False
        assert calls[0]["level"] == ValidationLevel.ERROR

    def test_invalid_rootfs_size_string(self, validator, report):
        """String rootfs size should trigger an error."""
        validator.validate(
            [_ct(ostemplate="s:vztmpl/t.tar.xz", rootfs={"storage": "local", "size": "8G"})]
        )
        calls = [
            c[1] for c in report.add_check.call_args_list if "rootfs" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is False


class TestNetworkNameValidation:
    """Tests for network name validation."""

    def test_network_with_name(self, validator, report):
        """Network with name should not trigger an error."""
        validator.validate(
            [_ct(ostemplate="s:vztmpl/t.tar.xz", network=[{"name": "eth0", "bridge": "vmbr0"}])]
        )
        nic_calls = [
            c[1] for c in report.add_check.call_args_list if "nic" in c[1].get("check_name", "")
        ]
        assert len(nic_calls) == 0

    def test_network_missing_name(self, validator, report):
        """Network without name should trigger an error."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", network=[{"bridge": "vmbr0"}])])
        calls = [
            c[1] for c in report.add_check.call_args_list if "nic" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is False
        assert calls[0]["level"] == ValidationLevel.ERROR
        assert "name" in calls[0]["message"]

    def test_single_dict_network_missing_name(self, validator, report):
        """Single dict network without name should trigger an error."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", network={"bridge": "vmbr0"})])
        calls = [
            c[1] for c in report.add_check.call_args_list if "nic" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is False


class TestMountPointValidation:
    """Tests for mount_point validation."""

    def test_valid_mount_point(self, validator, report):
        """Valid mount_point should not trigger an error."""
        validator.validate(
            [
                _ct(
                    ostemplate="s:vztmpl/t.tar.xz",
                    mount_point=[{"volume": "nas:data", "path": "/mnt/data"}],
                )
            ]
        )
        mp_calls = [
            c[1] for c in report.add_check.call_args_list if "mp" in c[1].get("check_name", "")
        ]
        assert len(mp_calls) == 0

    def test_mount_point_missing_volume(self, validator, report):
        """Mount point without volume should trigger an error."""
        validator.validate(
            [_ct(ostemplate="s:vztmpl/t.tar.xz", mount_point=[{"path": "/mnt/data"}])]
        )
        calls = [
            c[1] for c in report.add_check.call_args_list if "volume" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is False

    def test_mount_point_missing_path(self, validator, report):
        """Mount point without path should trigger an error."""
        validator.validate(
            [_ct(ostemplate="s:vztmpl/t.tar.xz", mount_point=[{"volume": "nas:data"}])]
        )
        calls = [
            c[1] for c in report.add_check.call_args_list if "path" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is False

    def test_mount_point_missing_both(self, validator, report):
        """Mount point without volume and path should trigger two errors."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", mount_point=[{}])])
        mp_calls = [
            c[1] for c in report.add_check.call_args_list if "mp" in c[1].get("check_name", "")
        ]
        assert len(mp_calls) == 2

    def test_single_dict_mount_point(self, validator, report):
        """Single dict mount_point should be handled."""
        validator.validate(
            [
                _ct(
                    ostemplate="s:vztmpl/t.tar.xz",
                    mount_point={"volume": "nas:data", "path": "/mnt/data"},
                )
            ]
        )
        mp_calls = [
            c[1] for c in report.add_check.call_args_list if "mp" in c[1].get("check_name", "")
        ]
        assert len(mp_calls) == 0


class TestFeaturesMountValidation:
    """Tests for features.mount validation."""

    def test_known_mount_types(self, validator, report):
        """Known mount types should not trigger a warning."""
        validator.validate(
            [
                _ct(
                    ostemplate="s:vztmpl/t.tar.xz",
                    features={"mount": ["nfs", "cifs"]},
                )
            ]
        )
        mount_calls = [
            c[1]
            for c in report.add_check.call_args_list
            if "feature_mount" in c[1].get("check_name", "")
        ]
        assert len(mount_calls) == 0

    def test_unknown_mount_type_warning(self, validator, report):
        """Unknown mount type should trigger a warning."""
        validator.validate(
            [_ct(ostemplate="s:vztmpl/t.tar.xz", features={"mount": ["nfs", "gluster"]})]
        )
        calls = [
            c[1]
            for c in report.add_check.call_args_list
            if "feature_mount" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is True
        assert calls[0]["level"] == ValidationLevel.WARNING
        assert "gluster" in calls[0]["message"]


class TestNumericFieldValidation:
    """Tests for cores, memory, and swap validation."""

    def test_valid_cores(self, validator, report):
        """Valid cores should not trigger an error."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", cores=2)])
        cores_calls = [
            c[1] for c in report.add_check.call_args_list if "cores" in c[1].get("check_name", "")
        ]
        assert len(cores_calls) == 0

    def test_invalid_cores_zero(self, validator, report):
        """Zero cores should trigger an error."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", cores=0)])
        calls = [
            c[1] for c in report.add_check.call_args_list if "cores" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is False

    def test_invalid_cores_negative(self, validator, report):
        """Negative cores should trigger an error."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", cores=-1)])
        calls = [
            c[1] for c in report.add_check.call_args_list if "cores" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is False
        assert calls[0]["level"] == ValidationLevel.ERROR

    def test_valid_memory(self, validator, report):
        """Valid memory should not trigger an error."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", memory=512)])
        memory_calls = [
            c[1] for c in report.add_check.call_args_list if "memory" in c[1].get("check_name", "")
        ]
        assert len(memory_calls) == 0

    def test_invalid_memory_zero(self, validator, report):
        """Zero memory should trigger an error."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", memory=0)])
        calls = [
            c[1] for c in report.add_check.call_args_list if "memory" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is False

    def test_valid_swap_zero(self, validator, report):
        """Zero swap (disabled) should be valid."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", swap=0)])
        swap_calls = [
            c[1] for c in report.add_check.call_args_list if "swap" in c[1].get("check_name", "")
        ]
        assert len(swap_calls) == 0

    def test_invalid_swap_negative(self, validator, report):
        """Negative swap should trigger an error."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", swap=-1)])
        calls = [
            c[1] for c in report.add_check.call_args_list if "swap" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is False
        assert calls[0]["level"] == ValidationLevel.ERROR


class TestCPUArchitectureValidation:
    """Tests for CPU architecture validation."""

    def test_known_arch(self, validator, report):
        """Known architecture should not trigger a warning."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", arch="amd64")])
        arch_calls = [
            c[1] for c in report.add_check.call_args_list if "arch" in c[1].get("check_name", "")
        ]
        assert len(arch_calls) == 0

    def test_unknown_arch_warning(self, validator, report):
        """Unknown architecture should trigger a warning."""
        validator.validate([_ct(ostemplate="s:vztmpl/t.tar.xz", arch="mips")])
        calls = [
            c[1] for c in report.add_check.call_args_list if "arch" in c[1].get("check_name", "")
        ]
        assert len(calls) == 1
        assert calls[0]["passed"] is True
        assert calls[0]["level"] == ValidationLevel.WARNING


class TestNonContainerResourcesSkipped:
    """Verify that non-container resources are skipped."""

    def test_vm_resource_skipped(self, validator, report):
        """VM resources should be ignored."""
        resource = ResourceConfig(
            name="test-vm",
            type="vm",
            provider="proxmox",
            config={"name": "test", "cores": -1},
        )
        validator.validate([resource])
        report.add_check.assert_not_called()

    def test_template_resource_skipped(self, validator, report):
        """Template resources should be ignored."""
        resource = ResourceConfig(
            name="test-template",
            type="template",
            provider="proxmox",
            config={"name": "test"},
        )
        validator.validate([resource])
        report.add_check.assert_not_called()


class TestValidContainerPasses:
    """Verify that a fully valid container produces no errors."""

    def test_valid_full_config(self, validator, report):
        """A fully configured valid container should produce no errors."""
        validator.validate(
            [
                _ct(
                    ostemplate="nas01:vztmpl/alpine-3.21-default_20250108_amd64.tar.xz",
                    ostype="alpine",
                    cores=2,
                    memory=256,
                    swap=0,
                    rootfs={"storage": "local-lvm", "size": 4},
                    network=[{"name": "eth0", "bridge": "vmbr0"}],
                    mount_point=[{"volume": "nas:data", "path": "/mnt/data"}],
                    features={"nesting": True, "mount": ["nfs"]},
                )
            ]
        )
        report.add_check.assert_not_called()
