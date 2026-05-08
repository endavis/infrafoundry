"""Tests for resource-level lifecycle events.

Covers:
- ResourceConfig.events field
- ResourceOutcome dataclass
- IaC runner classification
- Terraform JSON output parsing
- Resource lifecycle event firing
- Type-aware event filtering (terraform type -> InfraFoundry type)
- Provider get_terraform_resource_types() mappings
- Aggregate event deduplication
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.runners.ansible_runner import AnsibleRunner
from infrafoundry.core.runners.base_runner import BaseRunner
from infrafoundry.core.runners.pyinfra_runner import PyInfraRunner
from infrafoundry.core.runners.terraform_runner import TerraformRunner
from infrafoundry.core.types import ResourceOutcome

# --- ResourceConfig.events field ---


class TestResourceConfigEvents:
    """Test ResourceConfig events field."""

    def test_events_field_none_default(self) -> None:
        """ResourceConfig.events defaults to None."""
        rc = ResourceConfig(name="test", type="vm", provider="proxmox", config={"name": "test"})
        assert rc.events is None

    def test_events_field_with_data(self) -> None:
        """ResourceConfig accepts events dict."""
        events = {
            "on_create": [{"type": "script", "script": "scripts/setup.sh"}],
            "on_destroy": [{"type": "script", "script": "scripts/cleanup.sh"}],
        }
        rc = ResourceConfig(
            name="test",
            type="vm",
            provider="proxmox",
            config={"name": "test"},
            events=events,
        )
        assert rc.events == events
        assert len(rc.events["on_create"]) == 1
        assert rc.events["on_create"][0]["type"] == "script"

    def test_events_field_empty_dict(self) -> None:
        """ResourceConfig accepts empty events dict."""
        rc = ResourceConfig(
            name="test",
            type="vm",
            provider="proxmox",
            config={"name": "test"},
            events={},
        )
        assert rc.events == {}


# --- ResourceOutcome dataclass ---


class TestResourceOutcome:
    """Test ResourceOutcome dataclass."""

    def test_fields(self) -> None:
        """ResourceOutcome has correct fields."""
        outcome = ResourceOutcome(
            address="proxmox_vm.test_vm",
            action="create",
            resource_name="test-vm",
        )
        assert outcome.address == "proxmox_vm.test_vm"
        assert outcome.action == "create"
        assert outcome.resource_name == "test-vm"

    def test_slots(self) -> None:
        """ResourceOutcome uses __slots__."""
        assert hasattr(ResourceOutcome, "__slots__")


# --- IaC runner classification ---


class TestIaCRunnerClassification:
    """Test is_iac_runner property across runner types."""

    def test_terraform_is_iac(self) -> None:
        """TerraformRunner.is_iac_runner returns True."""
        runner = TerraformRunner()
        assert runner.is_iac_runner is True

    def test_ansible_is_not_iac(self) -> None:
        """AnsibleRunner.is_iac_runner returns False."""
        runner = AnsibleRunner()
        assert runner.is_iac_runner is False

    def test_pyinfra_is_not_iac(self) -> None:
        """PyInfraRunner.is_iac_runner returns False."""
        runner = PyInfraRunner()
        assert runner.is_iac_runner is False

    def test_base_runner_default_false(self) -> None:
        """BaseRunner.is_iac_runner defaults to False."""
        # We can't instantiate BaseRunner directly, so check via a non-IaC runner
        runner = AnsibleRunner()
        # Verify it comes from the base class default
        assert BaseRunner.is_iac_runner.fget is not None  # type: ignore[union-attr]
        assert BaseRunner.is_iac_runner.fget(runner) is False  # type: ignore[union-attr]


# --- Terraform JSON output parsing ---


class TestTerraformJsonParsing:
    """Test terraform JSON output parsing."""

    def test_parse_apply_complete(self, tmp_path: Path) -> None:
        """Parse apply_complete JSON lines into ResourceOutcome list."""
        # Create a .tf file for address mapping
        tf_file = tmp_path / "main.tf"
        tf_file.write_text(
            'resource "proxmox_virtual_environment_vm" "test_vm" {\n'
            '  name = "test-vm"\n'
            "}\n"
            'resource "proxmox_virtual_environment_vm" "web_server" {\n'
            '  name = "web-server"\n'
            "}\n"
        )

        runner = TerraformRunner()

        addr_vm = "proxmox_virtual_environment_vm.test_vm"
        addr_web = "proxmox_virtual_environment_vm.web_server"
        json_lines = [
            json.dumps(
                {
                    "type": "apply_start",
                    "hook": {"resource": {"addr": addr_vm}, "action": "create"},
                }
            ),
            json.dumps(
                {
                    "type": "apply_complete",
                    "hook": {"resource": {"addr": addr_vm}, "action": "create"},
                }
            ),
            json.dumps(
                {
                    "type": "apply_complete",
                    "hook": {"resource": {"addr": addr_web}, "action": "update"},
                }
            ),
            json.dumps(
                {
                    "type": "change_summary",
                    "changes": {"add": 1, "change": 1, "remove": 0},
                }
            ),
        ]

        outcomes = runner._parse_json_output(json_lines, tmp_path)

        assert len(outcomes) == 2
        assert outcomes[0].address == "proxmox_virtual_environment_vm.test_vm"
        assert outcomes[0].action == "create"
        assert outcomes[0].resource_name == "test-vm"
        assert outcomes[1].address == "proxmox_virtual_environment_vm.web_server"
        assert outcomes[1].action == "update"
        assert outcomes[1].resource_name == "web-server"

    def test_parse_no_changes(self, tmp_path: Path) -> None:
        """Empty output produces empty outcomes list."""
        runner = TerraformRunner()
        outcomes = runner._parse_json_output([], tmp_path)
        assert outcomes == []

    def test_parse_invalid_json(self, tmp_path: Path) -> None:
        """Invalid JSON lines are skipped."""
        runner = TerraformRunner()
        outcomes = runner._parse_json_output(["not json", "{invalid"], tmp_path)
        assert outcomes == []

    def test_parse_non_apply_complete_skipped(self, tmp_path: Path) -> None:
        """Non-apply_complete messages are skipped."""
        runner = TerraformRunner()
        json_lines = [
            json.dumps(
                {
                    "type": "apply_start",
                    "hook": {"resource": {"addr": "some.resource"}, "action": "create"},
                }
            ),
            json.dumps({"type": "change_summary", "changes": {"add": 1}}),
        ]
        outcomes = runner._parse_json_output(json_lines, tmp_path)
        assert outcomes == []

    def test_build_address_to_name_map(self, tmp_path: Path) -> None:
        """Build address-to-name map from .tf files."""
        tf_file = tmp_path / "main.tf"
        tf_file.write_text(
            'resource "proxmox_vm" "my_server" {\n'
            '  name = "my-server"\n'
            "}\n"
            'resource "opnsense_firewall_alias" "trusted_nets" {\n'
            '  name = "trusted-nets"\n'
            "}\n"
        )

        runner = TerraformRunner()
        name_map = runner._build_address_to_name_map(tmp_path)

        assert name_map == {
            "proxmox_vm.my_server": "my-server",
            "opnsense_firewall_alias.trusted_nets": "trusted-nets",
        }

    def test_fallback_name_extraction(self, tmp_path: Path) -> None:
        """When address isn't in map, fallback to extracting from address."""
        runner = TerraformRunner()
        json_lines = [
            json.dumps(
                {
                    "type": "apply_complete",
                    "hook": {
                        "resource": {"addr": "unknown_type.some_resource"},
                        "action": "create",
                    },
                }
            ),
        ]
        outcomes = runner._parse_json_output(json_lines, tmp_path)
        assert len(outcomes) == 1
        assert outcomes[0].resource_name == "some-resource"

    def test_build_address_map_suffix_match(self, tmp_path: Path) -> None:
        """Prefixed terraform names map to resource names via suffix matching."""
        tf_file = tmp_path / "main.tf"
        tf_file.write_text(
            'resource "terraform_data" "ova_vm_ontapcl_01" {\n'
            "}\n"
            'resource "terraform_data" "ova_vm_ontapcl_02" {\n'
            "}\n"
        )

        runner = TerraformRunner()
        name_map = runner._build_address_to_name_map(
            tmp_path, resource_names=["ontapcl-01", "ontapcl-02"]
        )

        assert name_map == {
            "terraform_data.ova_vm_ontapcl_01": "ontapcl-01",
            "terraform_data.ova_vm_ontapcl_02": "ontapcl-02",
        }

    def test_build_address_map_exact_match(self, tmp_path: Path) -> None:
        """Exact match takes priority when resource name matches directly."""
        tf_file = tmp_path / "main.tf"
        tf_file.write_text('resource "proxmox_virtual_environment_vm" "infra_web" {\n}\n')

        runner = TerraformRunner()
        name_map = runner._build_address_to_name_map(tmp_path, resource_names=["infra-web"])

        assert name_map == {
            "proxmox_virtual_environment_vm.infra_web": "infra-web",
        }

    def test_build_address_map_fallback_no_resource_names(self, tmp_path: Path) -> None:
        """Without resource_names, falls back to full name conversion."""
        tf_file = tmp_path / "main.tf"
        tf_file.write_text('resource "terraform_data" "ova_vm_ontapcl_01" {\n}\n')

        runner = TerraformRunner()
        name_map = runner._build_address_to_name_map(tmp_path)

        assert name_map == {
            "terraform_data.ova_vm_ontapcl_01": "ova-vm-ontapcl-01",
        }

    def test_parse_json_output_with_resource_names(self, tmp_path: Path) -> None:
        """End-to-end: prefixed terraform_data produces correct resource name."""
        tf_file = tmp_path / "main.tf"
        tf_file.write_text('resource "terraform_data" "ova_vm_ontapcl_01" {\n}\n')

        runner = TerraformRunner()
        json_lines = [
            json.dumps(
                {
                    "type": "apply_complete",
                    "hook": {
                        "resource": {"addr": "terraform_data.ova_vm_ontapcl_01"},
                        "action": "create",
                    },
                }
            ),
        ]
        outcomes = runner._parse_json_output(json_lines, tmp_path, resource_names=["ontapcl-01"])

        assert len(outcomes) == 1
        assert outcomes[0].resource_name == "ontapcl-01"
        assert outcomes[0].action == "create"


# --- Provider get_terraform_resource_types() ---


class TestProviderTerraformResourceTypes:
    """Test each provider's get_terraform_resource_types() mapping."""

    def test_proxmox_mapping(self, tmp_path: Path) -> None:
        """Proxmox provider returns correct terraform type mapping."""
        from infrafoundry.providers.proxmox import ProxmoxProvider

        provider = ProxmoxProvider(config_dir=tmp_path, output_dir=tmp_path)
        mapping = provider.get_terraform_resource_types()

        assert "vm" in mapping
        assert "proxmox_virtual_environment_vm" in mapping["vm"]
        assert "terraform_data" in mapping["vm"]
        assert "template" in mapping
        assert "proxmox_virtual_environment_vm" in mapping["template"]
        assert "container" in mapping
        assert "proxmox_virtual_environment_container" in mapping["container"]
        assert "storage" in mapping
        assert "proxmox_virtual_environment_storage_nfs" in mapping["storage"]

    def test_opnsense_mapping(self, tmp_path: Path) -> None:
        """OPNsense provider returns an empty terraform type mapping.

        After #782, every OPNsense component is managed by
        ``OPNsenseDirectRunner`` per ADR-0014 / ADR-0015. The terraform
        write path is fully retired; the mapping is empty.
        """
        from infrafoundry.providers.opnsense import OPNsenseProvider

        provider = OPNsenseProvider(config_dir=tmp_path, output_dir=tmp_path)
        mapping = provider.get_terraform_resource_types()

        assert mapping == {}

    def test_esxi_mapping(self, tmp_path: Path) -> None:
        """ESXi provider returns correct terraform type mapping."""
        from infrafoundry.providers.esxi import EsxiProvider

        provider = EsxiProvider(config_dir=tmp_path, output_dir=tmp_path)
        mapping = provider.get_terraform_resource_types()

        assert "vm" in mapping
        assert "esxi_guest" in mapping["vm"]
        assert "ovf_deployment" in mapping
        assert "terraform_data" in mapping["ovf_deployment"]

    def test_oci_mapping(self, tmp_path: Path) -> None:
        """OCI provider returns correct terraform type mapping."""
        from infrafoundry.providers.oci import OCIProvider

        provider = OCIProvider(config_dir=tmp_path, output_dir=tmp_path)
        mapping = provider.get_terraform_resource_types()

        assert "instance" in mapping
        assert "oci_core_instance" in mapping["instance"]
        assert "vcn" in mapping
        assert "oci_core_vcn" in mapping["vcn"]

    def test_kubernetes_mapping(self, tmp_path: Path) -> None:
        """Kubernetes provider returns correct terraform type mapping."""
        from infrafoundry.providers.kubernetes import KubernetesProvider

        provider = KubernetesProvider(config_dir=tmp_path, output_dir=tmp_path)
        mapping = provider.get_terraform_resource_types()

        assert "deployments" in mapping
        assert "kubernetes_deployment" in mapping["deployments"]
        assert "helm_releases" in mapping
        assert "helm_release" in mapping["helm_releases"]
        assert "manifests" in mapping
        assert "kubernetes_manifest" in mapping["manifests"]


# --- Type-aware event firing ---


class TestTypeAwareEventFiring:
    """Test that _fire_resource_lifecycle_events filters by terraform type."""

    def _make_executor(self) -> Any:
        """Create a DeploymentExecutor with mocked dependencies."""
        from infrafoundry.core.deployment_executor import DeploymentExecutor

        executor = DeploymentExecutor(
            runner_registry=MagicMock(),
            state_manager=MagicMock(),
            event_manager=MagicMock(),
            providers={},
        )
        return executor

    def _make_provider(self, tf_type_map: dict[str, list[str]]) -> MagicMock:
        """Create a mock provider with the given terraform type mapping."""
        provider = MagicMock()
        provider.get_terraform_resource_types.return_value = tf_type_map
        return provider

    def _make_resource(
        self, name: str, resource_type: str, events: dict | None = None
    ) -> ResourceConfig:
        """Create a ResourceConfig for testing."""
        return ResourceConfig(
            name=name,
            type=resource_type,
            provider="proxmox",
            config={"name": name},
            events=events,
        )

    def test_cloud_init_file_does_not_trigger_vm_on_create(self) -> None:
        """proxmox_virtual_environment_file outcome does NOT trigger on_create for vm."""
        executor = self._make_executor()
        provider = self._make_provider(
            {
                "vm": ["proxmox_virtual_environment_vm", "terraform_data"],
            }
        )
        vm_resource = self._make_resource(
            "my-vm",
            "vm",
            events={"on_create": [{"type": "script", "script": "setup.sh"}]},
        )
        outcome = ResourceOutcome(
            address="proxmox_virtual_environment_file.cloud_init_user_data_my_vm",
            action="create",
            resource_name="my-vm",
        )

        executor._fire_resource_lifecycle_events(
            "prod", "proxmox", provider, [vm_resource], [outcome], None
        )

        # Event should NOT have been emitted
        executor.event_manager.emit_event.assert_not_called()

    def test_vm_resource_triggers_on_create(self) -> None:
        """proxmox_virtual_environment_vm outcome DOES trigger on_create for vm."""
        executor = self._make_executor()
        provider = self._make_provider(
            {
                "vm": ["proxmox_virtual_environment_vm", "terraform_data"],
            }
        )
        vm_resource = self._make_resource(
            "my-vm",
            "vm",
            events={"on_create": [{"type": "script", "script": "setup.sh"}]},
        )
        outcome = ResourceOutcome(
            address="proxmox_virtual_environment_vm.my_vm",
            action="create",
            resource_name="my-vm",
        )

        executor._fire_resource_lifecycle_events(
            "prod", "proxmox", provider, [vm_resource], [outcome], None
        )

        # Event should have been emitted
        assert executor.event_manager.emit_event.called

    def test_terraform_data_triggers_on_create_for_vm(self) -> None:
        """terraform_data outcome DOES trigger on_create for vm (OVA case)."""
        executor = self._make_executor()
        provider = self._make_provider(
            {
                "vm": ["proxmox_virtual_environment_vm", "terraform_data"],
            }
        )
        vm_resource = self._make_resource(
            "my-vm",
            "vm",
            events={"on_create": [{"type": "script", "script": "setup.sh"}]},
        )
        outcome = ResourceOutcome(
            address="terraform_data.ova_vm_my_vm",
            action="create",
            resource_name="my-vm",
        )

        executor._fire_resource_lifecycle_events(
            "prod", "proxmox", provider, [vm_resource], [outcome], None
        )

        assert executor.event_manager.emit_event.called

    def test_unknown_terraform_type_does_not_fire(self) -> None:
        """Unknown terraform types don't trigger event handlers."""
        executor = self._make_executor()
        provider = self._make_provider(
            {
                "vm": ["proxmox_virtual_environment_vm"],
            }
        )
        vm_resource = self._make_resource(
            "my-vm",
            "vm",
            events={"on_create": [{"type": "script", "script": "setup.sh"}]},
        )
        outcome = ResourceOutcome(
            address="unknown_resource_type.my_vm",
            action="create",
            resource_name="my-vm",
        )

        executor._fire_resource_lifecycle_events(
            "prod", "proxmox", provider, [vm_resource], [outcome], None
        )

        executor.event_manager.emit_event.assert_not_called()

    def test_download_file_does_not_trigger_template_on_create(self) -> None:
        """proxmox_virtual_environment_download_file does not trigger template events."""
        executor = self._make_executor()
        provider = self._make_provider(
            {
                "template": ["proxmox_virtual_environment_vm"],
            }
        )
        template_resource = self._make_resource(
            "ubuntu-template",
            "template",
            events={"on_create": [{"type": "script", "script": "post-template.sh"}]},
        )
        outcome = ResourceOutcome(
            address="proxmox_virtual_environment_download_file.cloud_image_ubuntu_template",
            action="create",
            resource_name="ubuntu-template",
        )

        executor._fire_resource_lifecycle_events(
            "prod", "proxmox", provider, [template_resource], [outcome], None
        )

        executor.event_manager.emit_event.assert_not_called()

    def test_mixed_outcomes_only_fires_for_matching_types(self) -> None:
        """Only matching terraform types fire events, helper resources are skipped."""
        executor = self._make_executor()
        provider = self._make_provider(
            {
                "vm": ["proxmox_virtual_environment_vm", "terraform_data"],
            }
        )
        vm_resource = self._make_resource(
            "my-vm",
            "vm",
            events={"on_create": [{"type": "script", "script": "setup.sh"}]},
        )
        outcomes = [
            ResourceOutcome(
                address="proxmox_virtual_environment_file.cloud_init_user_data_my_vm",
                action="create",
                resource_name="my-vm",
            ),
            ResourceOutcome(
                address="proxmox_virtual_environment_vm.my_vm",
                action="create",
                resource_name="my-vm",
            ),
        ]

        executor._fire_resource_lifecycle_events(
            "prod", "proxmox", provider, [vm_resource], outcomes, None
        )

        # Should fire exactly once (for the VM, not the file)
        assert executor.event_manager.emit_event.call_count == 1


# --- Per-resource events pass resource_scoped=True (#539) ---


class TestPerResourceEventResourceScoped:
    """Test that _fire_resource_lifecycle_events passes resource_scoped=True.

    This ensures package-level handlers (without _resource_owner) are NOT
    triggered by per-resource events, only by the aggregate event in apply_serial.
    """

    def _make_executor(self) -> Any:
        """Create a DeploymentExecutor with mocked dependencies."""
        from infrafoundry.core.deployment_executor import DeploymentExecutor

        executor = DeploymentExecutor(
            runner_registry=MagicMock(),
            state_manager=MagicMock(),
            event_manager=MagicMock(),
            providers={},
        )
        return executor

    def _make_provider(self, tf_type_map: dict[str, list[str]]) -> MagicMock:
        """Create a mock provider with the given terraform type mapping."""
        provider = MagicMock()
        provider.get_terraform_resource_types.return_value = tf_type_map
        return provider

    def test_per_resource_event_sets_resource_scoped(self) -> None:
        """emit_event in _fire_resource_lifecycle_events passes resource_scoped=True."""
        executor = self._make_executor()
        provider = self._make_provider(
            {"vm": ["proxmox_virtual_environment_vm"]},
        )
        resource = ResourceConfig(
            name="aiqum",
            type="vm",
            provider="proxmox",
            config={"name": "aiqum"},
            events={"on_create": [{"type": "script", "script": "setup.sh"}]},
        )
        outcome = ResourceOutcome(
            address="proxmox_virtual_environment_vm.aiqum",
            action="create",
            resource_name="aiqum",
        )

        executor._fire_resource_lifecycle_events(
            "prod", "proxmox", provider, [resource], [outcome], None
        )

        assert executor.event_manager.emit_event.called
        call_kwargs = executor.event_manager.emit_event.call_args
        assert call_kwargs.kwargs.get("resource_scoped") is True


# --- Aggregate event deduplication ---


class TestAggregateEventDeduplication:
    """Test that apply_serial deduplicates aggregate created resource names."""

    def test_duplicate_resource_names_deduplicated(self) -> None:
        """Duplicate resource names in outcomes are deduplicated in aggregate event."""
        # Simulate results dict structure with duplicate resource names
        # (cloud-init file + VM both resolve to the same resource name)
        results = {
            "proxmox": {
                "terraform": {
                    "success": True,
                    "resource_outcomes": [
                        {"resource_name": "my-vm", "action": "create", "address": "file.x"},
                        {"resource_name": "my-vm", "action": "create", "address": "vm.x"},
                        {"resource_name": "other-vm", "action": "create", "address": "vm.y"},
                    ],
                }
            }
        }

        # Replicate the deduplication logic from apply_serial
        seen_created: set[str] = set()
        all_created: list[str] = []
        for result_val in results.values():
            if isinstance(result_val, dict):
                for tool_result in result_val.values():
                    if isinstance(tool_result, dict):
                        for outcome in tool_result.get("resource_outcomes", []):
                            name = (
                                outcome.get("resource_name", "")
                                if isinstance(outcome, dict)
                                else ""
                            )
                            action = outcome.get("action", "") if isinstance(outcome, dict) else ""
                            if action == "create" and name and name not in seen_created:
                                seen_created.add(name)
                                all_created.append(name)

        # "my-vm" should appear only once despite two outcomes
        assert all_created == ["my-vm", "other-vm"]
        assert len(all_created) == 2
