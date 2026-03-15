"""Tests for resource-level lifecycle events.

Covers:
- ResourceConfig.events field
- ResourceOutcome dataclass
- IaC runner classification
- Terraform JSON output parsing
- Resource lifecycle event firing
- AnsibleHandler creation and validation
- HandlerType.ANSIBLE enum
- Event bus ansible handler creation
"""

import json
from pathlib import Path

from infrafoundry.core.events.bus import UnifiedEventBus
from infrafoundry.core.events.handlers.ansible import AnsibleHandler
from infrafoundry.core.events.types import HandlerType
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
            "on_destroy": [{"type": "ansible", "playbook": "cleanup.yml"}],
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


# --- AnsibleHandler ---


class TestAnsibleHandler:
    """Test AnsibleHandler creation and validation."""

    def test_validate_config_valid(self) -> None:
        """Valid config passes validation."""
        handler = AnsibleHandler({"type": "ansible", "playbook": "playbooks/setup.yml"})
        errors = handler.validate_config()
        assert errors == []

    def test_validate_config_missing_playbook(self) -> None:
        """Missing playbook field fails validation."""
        handler = AnsibleHandler({"type": "ansible"})
        errors = handler.validate_config()
        assert len(errors) == 1
        assert "playbook" in errors[0].lower()

    def test_validate_config_bad_timeout(self) -> None:
        """Invalid timeout fails validation."""
        handler = AnsibleHandler({"type": "ansible", "playbook": "test.yml", "timeout": 0})
        errors = handler.validate_config()
        assert len(errors) == 1
        assert "timeout" in errors[0].lower()

    def test_handler_name(self) -> None:
        """Handler uses config name or class name."""
        handler = AnsibleHandler({"type": "ansible", "playbook": "test.yml", "name": "my-handler"})
        assert handler.name == "my-handler"

    def test_handler_default_name(self) -> None:
        """Handler defaults to class name."""
        handler = AnsibleHandler({"type": "ansible", "playbook": "test.yml"})
        assert handler.name == "AnsibleHandler"


# --- HandlerType.ANSIBLE ---


class TestHandlerTypeAnsible:
    """Test HandlerType enum includes ANSIBLE."""

    def test_ansible_value(self) -> None:
        """HandlerType.ANSIBLE has value 'ansible'."""
        assert HandlerType.ANSIBLE == "ansible"
        assert HandlerType.ANSIBLE.value == "ansible"


# --- Event bus ansible handler creation ---


class TestEventBusAnsibleHandler:
    """Test event bus creates AnsibleHandler correctly."""

    def test_creates_ansible_handler(self) -> None:
        """Event bus _create_handler creates AnsibleHandler for type=ansible."""
        bus = UnifiedEventBus()
        config = {"type": "ansible", "playbook": "playbooks/test.yml"}
        handler = bus._create_handler(config)
        assert isinstance(handler, AnsibleHandler)
        assert handler.config["playbook"] == "playbooks/test.yml"
