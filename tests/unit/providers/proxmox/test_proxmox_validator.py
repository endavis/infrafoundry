"""Unit tests for Proxmox ProxmoxValidator orchestration."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.core.validation_helpers import BaseAPIValidator
from infrafoundry.providers.proxmox.api_client import ProxmoxClient
from infrafoundry.providers.proxmox.validator import ProxmoxValidator
from infrafoundry.providers.proxmox.validators import (
    NetworkValidator,
    NodeValidator,
    StorageValidator,
    TemplateValidator,
    VMIDValidator,
)
from tests.helpers.env import make_env_config


@pytest.fixture
def env_config() -> Any:
    """Create a valid environment config."""
    return make_env_config(
        provider_settings={
            "proxmox": {
                "api_url": "https://pve.example.com:8006/api2/json",
                "api_token": "user@pam!token=secret",
                "node": "pve1",
            }
        },
    )


@pytest.fixture
def report() -> MagicMock:
    """Create a mock validation report."""
    return MagicMock(spec=ValidationReport)


@pytest.fixture
def validator(env_config: Any, report: MagicMock) -> ProxmoxValidator:
    """Create a ProxmoxValidator instance."""
    return ProxmoxValidator(env_config, report)


class TestComposition:
    """Tests for validator composition."""

    def test_api_validator_initialized(self, validator: ProxmoxValidator) -> None:
        """BaseAPIValidator is composed during init."""
        assert isinstance(validator.api_validator, BaseAPIValidator)

    def test_specialized_validators_initialized(self, validator: ProxmoxValidator) -> None:
        """All specialized validators are created."""
        assert isinstance(validator.node_validator, NodeValidator)
        assert isinstance(validator.storage_validator, StorageValidator)
        assert isinstance(validator.network_validator, NetworkValidator)
        assert isinstance(validator.template_validator, TemplateValidator)
        assert isinstance(validator.vmid_validator, VMIDValidator)


class TestValidateConnectivity:
    """Tests for validate_connectivity."""

    def test_missing_credentials_returns_early(self, validator: ProxmoxValidator) -> None:
        """Returns early when credentials are missing."""
        validator.api_validator.get_credentials = MagicMock(return_value=None)  # type: ignore[method-assign]

        validator.validate_connectivity()

        validator.api_validator.get_credentials.assert_called_once()

    def test_no_api_token_reports_error(self, report: MagicMock) -> None:
        """Reports error when no API token is available."""
        env_config = make_env_config(
            provider_settings={
                "proxmox": {
                    "api_url": "https://pve.example.com:8006/api2/json",
                    "node": "pve1",
                    # No api_token, api_token_id, or api_token_secret
                }
            },
        )
        validator = ProxmoxValidator(env_config, report)
        validator.api_validator.get_credentials = MagicMock(  # type: ignore[method-assign]
            return_value={"api_url": "https://pve.example.com:8006/api2/json", "node": "pve1"}
        )
        validator.api_validator.add_error = MagicMock()  # type: ignore[method-assign]

        validator.validate_connectivity()

        validator.api_validator.add_error.assert_called_once()
        call_args = validator.api_validator.add_error.call_args[1]
        assert "Missing API token" in call_args["message"]

    @patch("infrafoundry.providers.proxmox.api_client.requests.get")
    def test_success_reports_version(
        self, mock_get: MagicMock, validator: ProxmoxValidator
    ) -> None:
        """Reports success with version on successful API call."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"version": "8.1"}}
        mock_get.return_value = mock_response

        validator.api_validator.get_credentials = MagicMock(  # type: ignore[method-assign]
            return_value={"api_url": "https://pve.example.com:8006/api2/json", "node": "pve1"}
        )
        validator.api_validator.add_success = MagicMock()  # type: ignore[method-assign]

        validator.validate_connectivity()

        validator.api_validator.add_success.assert_called_once()
        call_args = validator.api_validator.add_success.call_args[1]
        assert "8.1" in call_args["message"]

    def test_api_error_reports_error(self, validator: ProxmoxValidator) -> None:
        """Reports error when API call fails."""
        validator.api_validator.get_credentials = MagicMock(  # type: ignore[method-assign]
            return_value={"api_url": "https://pve.example.com:8006/api2/json", "node": "pve1"}
        )
        validator.api_validator.add_error = MagicMock()  # type: ignore[method-assign]

        with patch.object(
            ProxmoxClient, "from_provider_settings", return_value=MagicMock()
        ) as mock_factory:
            mock_client = mock_factory.return_value
            mock_client.get_json.side_effect = APIError("connection refused", provider="proxmox")

            validator.validate_connectivity()

        validator.api_validator.add_error.assert_called_once()


class TestValidateReferences:
    """Tests for validate_references."""

    def test_no_client_returns_early(self, report: MagicMock) -> None:
        """Returns early when client can't be created."""
        env_config = make_env_config(
            provider_settings={
                "proxmox": {
                    "api_url": "https://pve.example.com:8006/api2/json",
                    "node": "pve1",
                    # No token
                }
            },
        )
        validator = ProxmoxValidator(env_config, report)

        validator.validate_references([])

        # No checks should have been added
        report.add_check.assert_not_called()

    def test_empty_resources(self, validator: ProxmoxValidator) -> None:
        """Handles empty resource list."""
        mock_client = MagicMock(spec=ProxmoxClient)
        mock_client.get_json.return_value = {"data": []}

        with patch.object(ProxmoxClient, "from_provider_settings", return_value=mock_client):
            validator.validate_references([])

    def test_delegates_to_specialized_validators(self, validator: ProxmoxValidator) -> None:
        """Delegates validation to specialized validators."""
        mock_client = MagicMock(spec=ProxmoxClient)
        mock_client.get_json.return_value = {"data": []}

        validator.node_validator = MagicMock()
        validator.storage_validator = MagicMock()
        validator.network_validator = MagicMock()
        validator.template_validator = MagicMock()
        validator.vmid_validator = MagicMock()

        resources = [
            ResourceConfig(
                name="vm1", type="vm", provider="proxmox", config={"target_node": "pve1"}
            ),
        ]

        with patch.object(ProxmoxClient, "from_provider_settings", return_value=mock_client):
            validator.validate_references(resources)

        validator.node_validator.validate.assert_called_once()
        validator.template_validator.validate.assert_called_once()
        validator.vmid_validator.validate.assert_called_once()

    def test_exception_caught_gracefully(self, validator: ProxmoxValidator) -> None:
        """Exceptions during validation are caught and reported."""
        mock_client = MagicMock(spec=ProxmoxClient)
        mock_client.get_json.side_effect = RuntimeError("unexpected")
        validator.api_validator.handle_validation_exception = MagicMock()  # type: ignore[method-assign]

        with patch.object(ProxmoxClient, "from_provider_settings", return_value=mock_client):
            validator.validate_references(
                [
                    ResourceConfig(
                        name="vm1", type="vm", provider="proxmox", config={"target_node": "pve1"}
                    ),
                ]
            )

        validator.api_validator.handle_validation_exception.assert_called_once()


class TestCollectResourceReferences:
    """Tests for _collect_resource_references."""

    def test_collects_target_node(self, validator: ProxmoxValidator) -> None:
        """Collects target node from resources."""
        resources = [
            ResourceConfig(
                name="vm1", type="vm", provider="proxmox", config={"target_node": "pve2"}
            ),
        ]

        refs = validator._collect_resource_references(resources, "pve1")

        assert "pve2" in refs.nodes

    def test_uses_default_node(self, validator: ProxmoxValidator) -> None:
        """Uses default node when target_node not specified."""
        resources = [
            ResourceConfig(name="vm1", type="vm", provider="proxmox", config={}),
        ]

        refs = validator._collect_resource_references(resources, "pve1")

        assert "pve1" in refs.nodes

    def test_collects_disk_storage(self, validator: ProxmoxValidator) -> None:
        """Collects storage from disk config."""
        resources = [
            ResourceConfig(
                name="vm1",
                type="vm",
                provider="proxmox",
                config={"target_node": "pve1", "disk": {"storage": "local-lvm", "size": "32G"}},
            ),
        ]

        refs = validator._collect_resource_references(resources, None)

        assert ("pve1", "local-lvm") in refs.storage_pools

    def test_collects_rootfs_storage(self, validator: ProxmoxValidator) -> None:
        """Collects storage from container rootfs config."""
        resources = [
            ResourceConfig(
                name="ct1",
                type="container",
                provider="proxmox",
                config={"target_node": "pve1", "rootfs": {"storage": "local-lvm", "size": "8G"}},
            ),
        ]

        refs = validator._collect_resource_references(resources, None)

        assert ("pve1", "local-lvm") in refs.storage_pools

    def test_collects_top_level_storage(self, validator: ProxmoxValidator) -> None:
        """Collects top-level storage field."""
        resources = [
            ResourceConfig(
                name="vm1",
                type="vm",
                provider="proxmox",
                config={"target_node": "pve1", "storage": "ceph"},
            ),
        ]

        refs = validator._collect_resource_references(resources, None)

        assert ("pve1", "ceph") in refs.storage_pools

    def test_collects_network_dict_bridge(self, validator: ProxmoxValidator) -> None:
        """Collects bridge from network dict config."""
        resources = [
            ResourceConfig(
                name="vm1",
                type="vm",
                provider="proxmox",
                config={"target_node": "pve1", "network": {"bridge": "vmbr0"}},
            ),
        ]

        refs = validator._collect_resource_references(resources, None)

        assert ("pve1", "vmbr0") in refs.bridges

    def test_collects_network_list_bridges(self, validator: ProxmoxValidator) -> None:
        """Collects bridges from network list config."""
        resources = [
            ResourceConfig(
                name="vm1",
                type="vm",
                provider="proxmox",
                config={
                    "target_node": "pve1",
                    "network": [{"bridge": "vmbr0"}, {"bridge": "vmbr1"}],
                },
            ),
        ]

        refs = validator._collect_resource_references(resources, None)

        assert ("pve1", "vmbr0") in refs.bridges
        assert ("pve1", "vmbr1") in refs.bridges

    def test_collects_clone_scalar(self, validator: ProxmoxValidator) -> None:
        """Collects template ref from scalar clone value."""
        resources = [
            ResourceConfig(
                name="vm1", type="vm", provider="proxmox", config={"clone": "ubuntu-22.04"}
            ),
        ]

        refs = validator._collect_resource_references(resources, "pve1")

        assert "ubuntu-22.04" in refs.template_refs
        assert "vm1" in refs.template_refs["ubuntu-22.04"]

    def test_collects_clone_dict(self, validator: ProxmoxValidator) -> None:
        """Collects template ref from dict clone value."""
        resources = [
            ResourceConfig(
                name="vm1",
                type="vm",
                provider="proxmox",
                config={"clone": {"vm_id": 100}},
            ),
        ]

        refs = validator._collect_resource_references(resources, "pve1")

        assert "100" in refs.template_refs

    def test_collects_vmid(self, validator: ProxmoxValidator) -> None:
        """Collects VMID from resource."""
        resources = [
            ResourceConfig(name="vm1", type="vm", provider="proxmox", config={"vmid": 200}),
        ]

        refs = validator._collect_resource_references(resources, "pve1")

        assert 200 in refs.vmids
        assert refs.vmids[200] == "vm1"

    def test_duplicate_vmid_reports_error(
        self, validator: ProxmoxValidator, report: MagicMock
    ) -> None:
        """Reports error for duplicate VMIDs."""
        resources = [
            ResourceConfig(name="vm1", type="vm", provider="proxmox", config={"vmid": 200}),
            ResourceConfig(name="vm2", type="vm", provider="proxmox", config={"vmid": 200}),
        ]

        validator._collect_resource_references(resources, "pve1")

        report.add_check.assert_called()
        calls = [c for c in report.add_check.call_args_list if "duplicate" in str(c)]
        assert len(calls) == 1
        assert calls[0][1]["passed"] is False

    def test_collects_mac_address(self, validator: ProxmoxValidator) -> None:
        """Collects MAC addresses from NICs."""
        resources = [
            ResourceConfig(
                name="vm1",
                type="vm",
                provider="proxmox",
                config={
                    "target_node": "pve1",
                    "network": {"bridge": "vmbr0", "macaddr": "AA:BB:CC:DD:EE:FF"},
                },
            ),
        ]

        refs = validator._collect_resource_references(resources, None)

        assert "AA:BB:CC:DD:EE:FF" in refs.mac_addresses

    def test_duplicate_mac_reports_error(
        self, validator: ProxmoxValidator, report: MagicMock
    ) -> None:
        """Reports error for duplicate MAC addresses."""
        resources = [
            ResourceConfig(
                name="vm1",
                type="vm",
                provider="proxmox",
                config={
                    "target_node": "pve1",
                    "network": {"bridge": "vmbr0", "macaddr": "AA:BB:CC:DD:EE:FF"},
                },
            ),
            ResourceConfig(
                name="vm2",
                type="vm",
                provider="proxmox",
                config={
                    "target_node": "pve1",
                    "network": {"bridge": "vmbr0", "macaddr": "aa:bb:cc:dd:ee:ff"},
                },
            ),
        ]

        validator._collect_resource_references(resources, None)

        calls = [c for c in report.add_check.call_args_list if "duplicate" in str(c)]
        assert len(calls) == 1
        assert calls[0][1]["passed"] is False

    def test_container_ctid_collected(self, validator: ProxmoxValidator) -> None:
        """Collects CTID from container resources."""
        resources = [
            ResourceConfig(name="ct1", type="container", provider="proxmox", config={"ctid": 300}),
        ]

        refs = validator._collect_resource_references(resources, "pve1")

        assert 300 in refs.vmids


class TestGetClusterVMs:
    """Tests for _get_cluster_vms."""

    def test_success_returns_data(self, validator: ProxmoxValidator) -> None:
        """Returns VM data on successful API call."""
        mock_client = MagicMock(spec=ProxmoxClient)
        mock_client.get_json.return_value = {
            "data": [
                {"vmid": 100, "name": "template-1", "template": 1},
                {"vmid": 200, "name": "vm-1", "template": 0},
            ]
        }

        result = validator._get_cluster_vms(mock_client)

        assert result is not None
        assert len(result) == 2
        assert result[0].get("vmid") == 100

    def test_api_error_returns_none(self, validator: ProxmoxValidator, report: MagicMock) -> None:
        """Returns None and reports warning on API error."""
        mock_client = MagicMock(spec=ProxmoxClient)
        mock_client.get_json.side_effect = APIError("failed", provider="proxmox")

        result = validator._get_cluster_vms(mock_client)

        assert result is None
        report.add_check.assert_called_once()
        call_args = report.add_check.call_args[1]
        assert call_args["passed"] is False
        assert call_args["level"] == ValidationLevel.WARNING

    def test_cache_hit(self, validator: ProxmoxValidator) -> None:
        """Returns cached data on subsequent calls."""
        mock_client = MagicMock(spec=ProxmoxClient)
        mock_client.get_json.return_value = {"data": [{"vmid": 100}]}

        result1 = validator._get_cluster_vms(mock_client)
        result2 = validator._get_cluster_vms(mock_client)

        assert result1 == result2
        mock_client.get_json.assert_called_once()
