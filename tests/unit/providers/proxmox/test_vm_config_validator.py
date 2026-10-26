"""Unit tests for Proxmox VMConfigValidator."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.proxmox.validators.vm_config_validator import VMConfigValidator


@pytest.fixture
def report() -> MagicMock:
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(report: MagicMock) -> VMConfigValidator:
    """Create a VMConfigValidator instance."""
    return VMConfigValidator(report)


def _vm(name: str = "test-vm", **config: Any) -> ResourceConfig:
    """Helper to create a VM ResourceConfig."""
    return ResourceConfig(
        name=name,
        type="vm",
        provider="proxmox",
        config={"name": name, "target_node": "pve01", **config},
    )


class TestCPUTypeValidation:
    """Tests for cpu_type validation."""

    def test_known_cpu_type_no_warning(
        self, validator: VMConfigValidator, report: MagicMock
    ) -> None:
        """Known cpu_type should not trigger a warning."""
        validator.validate([_vm(cpu_type="host")])
        report.add_check.assert_not_called()

    def test_unknown_cpu_type_warning(
        self, validator: VMConfigValidator, report: MagicMock
    ) -> None:
        """Unknown cpu_type should trigger a warning (not error)."""
        validator.validate([_vm(cpu_type="custom-cpu")])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is True  # Warning, not error
        assert call_args["level"] == ValidationLevel.WARNING
        assert "custom-cpu" in call_args["message"]

    def test_no_cpu_type_no_check(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """No cpu_type should not trigger any check."""
        validator.validate([_vm()])
        # No cpu_type-related check should be added
        for call in report.add_check.call_args_list:
            assert "cpu_type" not in call[1].get("check_name", "")


class TestMachineValidation:
    """Tests for machine type validation."""

    def test_valid_machine_q35(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """q35 machine type should not trigger an error."""
        validator.validate([_vm(machine="q35")])
        report.add_check.assert_not_called()

    def test_valid_machine_i440fx(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """i440fx machine type should not trigger an error."""
        validator.validate([_vm(machine="i440fx")])
        report.add_check.assert_not_called()

    def test_invalid_machine(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """Invalid machine type should trigger an error."""
        validator.validate([_vm(machine="invalid")])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert call_args["level"] == ValidationLevel.ERROR
        assert "invalid" in call_args["message"]


class TestBIOSValidation:
    """Tests for BIOS type validation."""

    def test_valid_bios_seabios(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """seabios should not trigger an error."""
        validator.validate([_vm(bios="seabios")])
        report.add_check.assert_not_called()

    def test_valid_bios_ovmf(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """ovmf should not trigger an error (but may trigger efi_disk warning)."""
        validator.validate([_vm(bios="ovmf")])
        # Only the ovmf_efi_disk warning, not a bios error
        for call in report.add_check.call_args_list:
            assert "bios" not in call[1].get("check_name", "") or "ovmf_efi_disk" in call[1].get(
                "check_name", ""
            )

    def test_invalid_bios(self, validator: VMConfigValidator, report: MagicMock) -> None:
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

    def test_valid_balloon_zero(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """Balloon = 0 (disabled) should be valid."""
        validator.validate([_vm(balloon=0)])
        report.add_check.assert_not_called()

    def test_valid_balloon_positive(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """Positive balloon value should be valid."""
        validator.validate([_vm(balloon=2048)])
        report.add_check.assert_not_called()

    def test_invalid_balloon_negative(
        self, validator: VMConfigValidator, report: MagicMock
    ) -> None:
        """Negative balloon should trigger an error."""
        validator.validate([_vm(balloon=-1)])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert call_args["level"] == ValidationLevel.ERROR

    def test_invalid_balloon_string(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """Non-integer balloon should trigger an error."""
        validator.validate([_vm(balloon="not-a-number")])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False


class TestISOValidation:
    """Tests for ISO path validation."""

    def test_valid_iso_path(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """Valid ISO path should not trigger an error."""
        validator.validate([_vm(iso="local:iso/ubuntu-24.04.iso")])
        report.add_check.assert_not_called()

    def test_valid_iso_path_with_dashes(
        self, validator: VMConfigValidator, report: MagicMock
    ) -> None:
        """ISO path with dashes and underscores should be valid."""
        validator.validate([_vm(iso="nas-01:iso/my_image.iso")])
        report.add_check.assert_not_called()

    def test_invalid_iso_path(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """Invalid ISO path should trigger an error."""
        validator.validate([_vm(iso="/path/to/ubuntu.iso")])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert call_args["level"] == ValidationLevel.ERROR

    def test_invalid_iso_no_extension(
        self, validator: VMConfigValidator, report: MagicMock
    ) -> None:
        """ISO path without .iso extension should trigger an error."""
        validator.validate([_vm(iso="local:iso/ubuntu")])
        report.add_check.assert_called_once()


class TestDiskTypeValidation:
    """Tests for disk type validation."""

    def test_valid_disk_types(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """All valid disk types should pass."""
        for disk_type in ("virtio", "scsi", "sata"):
            report.reset_mock()
            validator.validate([_vm(disk={"storage": "local-lvm", "type": disk_type})])
            report.add_check.assert_not_called()

    def test_invalid_disk_type(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """Invalid disk type should trigger an error."""
        validator.validate([_vm(disk={"storage": "local-lvm", "type": "ide"})])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert "ide" in call_args["message"]


class TestNetworkModelValidation:
    """Tests for network model validation."""

    def test_valid_nic_models(self, validator: VMConfigValidator, report: MagicMock) -> None:
        """All valid NIC models should not trigger warnings."""
        for model in ("virtio", "e1000", "e1000e", "rtl8139", "vmxnet3"):
            report.reset_mock()
            validator.validate([_vm(network=[{"bridge": "vmbr0", "model": model}])])
            report.add_check.assert_not_called()

    def test_unknown_nic_model_warning(
        self, validator: VMConfigValidator, report: MagicMock
    ) -> None:
        """Unknown NIC model should trigger a warning."""
        validator.validate([_vm(network=[{"bridge": "vmbr0", "model": "ne2k_pci"}])])
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is True  # Warning, not error
        assert call_args["level"] == ValidationLevel.WARNING

    def test_nic_without_model_no_check(
        self, validator: VMConfigValidator, report: MagicMock
    ) -> None:
        """NIC without model should not trigger any model check."""
        validator.validate([_vm(network=[{"bridge": "vmbr0"}])])
        model_calls = [
            c for c in report.add_check.call_args_list if "model" in str(c[1].get("check_name", ""))
        ]
        assert len(model_calls) == 0

    def test_multi_nic_model_validation(
        self, validator: VMConfigValidator, report: MagicMock
    ) -> None:
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

    def test_dict_network_model_validation(
        self, validator: VMConfigValidator, report: MagicMock
    ) -> None:
        """Single dict network with unknown model should trigger warning."""
        validator.validate([_vm(network={"bridge": "vmbr0", "model": "unknown"})])
        report.add_check.assert_called_once()
        assert report.add_check.call_args[1]["level"] == ValidationLevel.WARNING


class TestOVMFEFIDiskWarning:
    """Tests for OVMF without EFI disk warning."""

    def test_ovmf_without_efi_disk_warning(
        self, validator: VMConfigValidator, report: MagicMock
    ) -> None:
        """OVMF without efi_disk should produce a warning."""
        validator.validate([_vm(bios="ovmf")])
        calls = [c[1] for c in report.add_check.call_args_list]
        efi_calls = [c for c in calls if "ovmf_efi_disk" in c["check_name"]]
        assert len(efi_calls) == 1
        assert efi_calls[0]["passed"] is True
        assert efi_calls[0]["level"] == ValidationLevel.WARNING

    def test_ovmf_with_efi_disk_no_warning(
        self, validator: VMConfigValidator, report: MagicMock
    ) -> None:
        """OVMF with efi_disk should not produce the warning."""
        validator.validate([_vm(bios="ovmf", efi_disk={"storage": "local-lvm"})])
        calls = [c[1] for c in report.add_check.call_args_list]
        efi_calls = [c for c in calls if "ovmf_efi_disk" in c["check_name"]]
        assert len(efi_calls) == 0

    def test_seabios_no_efi_disk_warning(
        self, validator: VMConfigValidator, report: MagicMock
    ) -> None:
        """SeaBIOS without efi_disk should not produce a warning."""
        validator.validate([_vm(bios="seabios")])
        report.add_check.assert_not_called()


class TestNonVMResourcesSkipped:
    """Verify that non-VM resources are skipped."""

    def test_template_resource_skipped(
        self, validator: VMConfigValidator, report: MagicMock
    ) -> None:
        """Template resources should be ignored."""
        resource = ResourceConfig(
            name="test-template",
            type="template",
            provider="proxmox",
            config={"name": "test", "machine": "invalid"},
        )
        validator.validate([resource])
        report.add_check.assert_not_called()


class TestDiskImageValidation:
    """Tests for ``disk_image_source`` / ``disk_image_sha256`` (#1094)."""

    URL = "https://pkg.opnsense.org/releases/26.1/OPNsense-26.1.6-nano-amd64.img.bz2"

    @pytest.mark.parametrize("source", [URL, "/mnt/pve/infra/fw.img", "http://mirror/x.img"])
    def test_valid_sources_pass(
        self, validator: VMConfigValidator, report: MagicMock, source: str
    ) -> None:
        validator.validate([_vm(disk_image_source=source, disk_image_sha256="0" * 64)])
        report.add_check.assert_not_called()

    @pytest.mark.parametrize(
        ("config", "check", "fragment"),
        [
            ({"disk_image_source": "fw.img"}, "disk_image_source", "absolute path"),
            ({"disk_image_source": "/x/fw.iso"}, "disk_image_source", ".img or .img.bz2"),
            (
                {"disk_image_source": URL, "ova_source": "/x/a.ova"},
                "disk_image_source",
                "mutually exclusive",
            ),
            ({"disk_image_source": URL, "disk_image_sha256": "ABC"}, "disk_image_sha256", "64"),
            ({"disk_image_sha256": "0" * 64}, "disk_image_sha256", "needs disk_image_source"),
        ],
    )
    def test_invalid_config_is_an_error(
        self,
        validator: VMConfigValidator,
        report: MagicMock,
        config: dict[str, Any],
        check: str,
        fragment: str,
    ) -> None:
        validator.validate([_vm(**config)])

        call = report.add_check.call_args.kwargs
        assert call["check_name"] == f"proxmox_vm_test-vm_{check}"
        assert call["passed"] is False
        assert call["level"] is ValidationLevel.ERROR
        assert fragment in call["message"]
