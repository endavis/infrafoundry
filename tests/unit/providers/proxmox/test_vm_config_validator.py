"""Unit tests for Proxmox VMConfigValidator."""

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.proxmox.validators.vm_config_validator import VMConfigValidator


@pytest.fixture
def report():
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report):
    """Create a VMConfigValidator instance."""
    return VMConfigValidator(report)


def _vm(name: str = "test-vm", **config) -> ResourceConfig:
    """Helper to create a VM ResourceConfig."""
    return ResourceConfig(
        name=name,
        type="vm",
        provider="proxmox",
        config={"name": name, "target_node": "pve01", **config},
    )


class TestCPUTypeValidation:
    """Tests for cpu_type validation."""

    def test_known_cpu_type_no_warning(self, validator, report):
        """Known cpu_type should not trigger a warning."""
        validator.validate([_vm(cpu_type="host")])
        report.add_check.assert_not_called()

    def test_unknown_cpu_type_warning(self, validator, report):
        """Unknown cpu_type should trigger a warning (not error)."""
        validator.validate([_vm(cpu_type="custom-cpu")])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is True  # Warning, not error
        assert call_args["level"] == ValidationLevel.WARNING
        assert "custom-cpu" in call_args["message"]

    def test_no_cpu_type_no_check(self, validator, report):
        """No cpu_type should not trigger any check."""
        validator.validate([_vm()])
        # No cpu_type-related check should be added
        for call in report.add_check.call_args_list:
            assert "cpu_type" not in call[1].get("check_name", "")


class TestMachineValidation:
    """Tests for machine type validation."""

    def test_valid_machine_q35(self, validator, report):
        """q35 machine type should not trigger an error."""
        validator.validate([_vm(machine="q35")])
        report.add_check.assert_not_called()

    def test_valid_machine_i440fx(self, validator, report):
        """i440fx machine type should not trigger an error."""
        validator.validate([_vm(machine="i440fx")])
        report.add_check.assert_not_called()

    def test_invalid_machine(self, validator, report):
        """Invalid machine type should trigger an error."""
        validator.validate([_vm(machine="invalid")])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert call_args["level"] == ValidationLevel.ERROR
        assert "invalid" in call_args["message"]


class TestBIOSValidation:
    """Tests for BIOS type validation."""

    def test_valid_bios_seabios(self, validator, report):
        """seabios should not trigger an error."""
        validator.validate([_vm(bios="seabios")])
        report.add_check.assert_not_called()

    def test_valid_bios_ovmf(self, validator, report):
        """ovmf should not trigger an error (but may trigger efi_disk warning)."""
        validator.validate([_vm(bios="ovmf")])
        # Only the ovmf_efi_disk warning, not a bios error
        for call in report.add_check.call_args_list:
            assert "bios" not in call[1].get("check_name", "") or "ovmf_efi_disk" in call[1].get(
                "check_name", ""
            )

    def test_invalid_bios(self, validator, report):
        """Invalid BIOS should trigger an error."""
        validator.validate([_vm(bios="legacy")])
        calls = [c[1] for c in report.add_check.call_args_list]
        bios_calls = [
            c for c in calls if "bios" in c["check_name"] and "efi" not in c["check_name"]
        ]
        assert len(bios_calls) == 1
        assert bios_calls[0]["passed"] is False
        assert bios_calls[0]["level"] == ValidationLevel.ERROR


class TestBalloonValidation:
    """Tests for balloon validation."""

    def test_valid_balloon_zero(self, validator, report):
        """Balloon = 0 (disabled) should be valid."""
        validator.validate([_vm(balloon=0)])
        report.add_check.assert_not_called()

    def test_valid_balloon_positive(self, validator, report):
        """Positive balloon value should be valid."""
        validator.validate([_vm(balloon=2048)])
        report.add_check.assert_not_called()

    def test_invalid_balloon_negative(self, validator, report):
        """Negative balloon should trigger an error."""
        validator.validate([_vm(balloon=-1)])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert call_args["level"] == ValidationLevel.ERROR

    def test_invalid_balloon_string(self, validator, report):
        """Non-integer balloon should trigger an error."""
        validator.validate([_vm(balloon="not-a-number")])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False


class TestISOValidation:
    """Tests for ISO path validation."""

    def test_valid_iso_path(self, validator, report):
        """Valid ISO path should not trigger an error."""
        validator.validate([_vm(iso="local:iso/ubuntu-24.04.iso")])
        report.add_check.assert_not_called()

    def test_valid_iso_path_with_dashes(self, validator, report):
        """ISO path with dashes and underscores should be valid."""
        validator.validate([_vm(iso="nas-01:iso/my_image.iso")])
        report.add_check.assert_not_called()

    def test_invalid_iso_path(self, validator, report):
        """Invalid ISO path should trigger an error."""
        validator.validate([_vm(iso="/path/to/ubuntu.iso")])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert call_args["level"] == ValidationLevel.ERROR

    def test_invalid_iso_no_extension(self, validator, report):
        """ISO path without .iso extension should trigger an error."""
        validator.validate([_vm(iso="local:iso/ubuntu")])
        report.add_check.assert_called_once()


class TestDiskTypeValidation:
    """Tests for disk type validation."""

    def test_valid_disk_types(self, validator, report):
        """All valid disk types should pass."""
        for disk_type in ("virtio", "scsi", "sata"):
            report.reset_mock()
            validator.validate([_vm(disk={"storage": "local-lvm", "type": disk_type})])
            report.add_check.assert_not_called()

    def test_invalid_disk_type(self, validator, report):
        """Invalid disk type should trigger an error."""
        validator.validate([_vm(disk={"storage": "local-lvm", "type": "ide"})])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert "ide" in call_args["message"]


class TestNetworkModelValidation:
    """Tests for network model validation."""

    def test_valid_nic_models(self, validator, report):
        """All valid NIC models should not trigger warnings."""
        for model in ("virtio", "e1000", "e1000e", "rtl8139", "vmxnet3"):
            report.reset_mock()
            validator.validate([_vm(network=[{"bridge": "vmbr0", "model": model}])])
            report.add_check.assert_not_called()

    def test_unknown_nic_model_warning(self, validator, report):
        """Unknown NIC model should trigger a warning."""
        validator.validate([_vm(network=[{"bridge": "vmbr0", "model": "ne2k_pci"}])])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is True  # Warning, not error
        assert call_args["level"] == ValidationLevel.WARNING

    def test_nic_without_model_no_check(self, validator, report):
        """NIC without model should not trigger any model check."""
        validator.validate([_vm(network=[{"bridge": "vmbr0"}])])
        model_calls = [
            c for c in report.add_check.call_args_list if "model" in str(c[1].get("check_name", ""))
        ]
        assert len(model_calls) == 0

    def test_multi_nic_model_validation(self, validator, report):
        """Multiple NICs with unknown models should each get a warning."""
        validator.validate(
            [
                _vm(
                    network=[
                        {"bridge": "vmbr0", "model": "unknown1"},
                        {"bridge": "vmbr1", "model": "unknown2"},
                    ]
                )
            ]
        )
        model_calls = [
            c for c in report.add_check.call_args_list if "nic" in str(c[1].get("check_name", ""))
        ]
        assert len(model_calls) == 2

    def test_dict_network_model_validation(self, validator, report):
        """Single dict network with unknown model should trigger warning."""
        validator.validate([_vm(network={"bridge": "vmbr0", "model": "unknown"})])
        report.add_check.assert_called_once()
        assert report.add_check.call_args[1]["level"] == ValidationLevel.WARNING


class TestOVMFEFIDiskWarning:
    """Tests for OVMF without EFI disk warning."""

    def test_ovmf_without_efi_disk_warning(self, validator, report):
        """OVMF without efi_disk should produce a warning."""
        validator.validate([_vm(bios="ovmf")])
        calls = [c[1] for c in report.add_check.call_args_list]
        efi_calls = [c for c in calls if "ovmf_efi_disk" in c["check_name"]]
        assert len(efi_calls) == 1
        assert efi_calls[0]["passed"] is True
        assert efi_calls[0]["level"] == ValidationLevel.WARNING

    def test_ovmf_with_efi_disk_no_warning(self, validator, report):
        """OVMF with efi_disk should not produce the warning."""
        validator.validate([_vm(bios="ovmf", efi_disk={"storage": "local-lvm"})])
        calls = [c[1] for c in report.add_check.call_args_list]
        efi_calls = [c for c in calls if "ovmf_efi_disk" in c["check_name"]]
        assert len(efi_calls) == 0

    def test_seabios_no_efi_disk_warning(self, validator, report):
        """SeaBIOS without efi_disk should not produce a warning."""
        validator.validate([_vm(bios="seabios")])
        report.add_check.assert_not_called()


class TestNonVMResourcesSkipped:
    """Verify that non-VM resources are skipped."""

    def test_template_resource_skipped(self, validator, report):
        """Template resources should be ignored."""
        resource = ResourceConfig(
            name="test-template",
            type="template",
            provider="proxmox",
            config={"name": "test", "machine": "invalid"},
        )
        validator.validate([resource])
        report.add_check.assert_not_called()
