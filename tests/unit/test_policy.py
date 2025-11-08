"""Unit tests for PolicyEngine."""

import pytest
import yaml

from infrafoundry.core.policy import PolicyEngine, PolicyLevel, PolicyViolation, PolicyType
from infrafoundry.core.provider import ResourceConfig


@pytest.mark.unit
class TestPolicyEngine:
    """Tests for PolicyEngine."""

    def test_init(self, mock_policy_dir):
        """Test PolicyEngine initialization."""
        engine = PolicyEngine(mock_policy_dir)
        assert len(engine.policies) > 0

    def test_load_policies(self, mock_policy_dir):
        """Test loading policies from directory."""
        engine = PolicyEngine(mock_policy_dir)
        policy_names = {p.name for p in engine.policies}
        assert "resource_limits" in policy_names
        assert "require_tags" in policy_names

    def test_validate_resource_limits(self, mock_policy_dir):
        """Test resource limits policy."""
        engine = PolicyEngine(mock_policy_dir)

        # Create ResourceConfig objects (within limits)
        resource = ResourceConfig(
            provider="proxmox",
            type="vm",
            name="vm-01",
            config={"cores": 8, "memory": 16384}
        )
        violations = engine.evaluate_resources([resource], "dev")
        # No violations
        cores_violations = [v for v in violations if "cores" in v.message]
        assert len(cores_violations) == 0

        # Resource exceeding limits
        resource2 = ResourceConfig(
            provider="proxmox",
            type="vm",
            name="vm-02",
            config={"cores": 32, "memory": 131072}
        )
        violations = engine.evaluate_resources([resource2], "dev")
        assert len(violations) > 0

    def test_validate_required_tags(self, mock_policy_dir):
        """Test required tags policy."""
        engine = PolicyEngine(mock_policy_dir)

        # Resource with all required tags (as string format)
        resource = ResourceConfig(
            provider="proxmox",
            type="vm",
            name="vm-01",
            config={
                "cores": 4,
                "tags": "environment, owner, project"  # String format
            }
        )
        violations = engine.evaluate_resources([resource], "dev")
        tag_violations = [v for v in violations if "tag" in v.message.lower()]
        assert len(tag_violations) == 0

        # Resource missing required tags
        resource2 = ResourceConfig(
            provider="proxmox",
            type="vm",
            name="vm-02",
            config={"cores": 4, "tags": "environment"}  # Missing owner and project
        )
        violations = engine.evaluate_resources([resource2], "dev")
        tag_violations = [v for v in violations if "tag" in v.message.lower()]
        assert len(tag_violations) > 0

    def test_policy_level_enforcement(self, temp_dir):
        """Test different policy enforcement levels."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        # Warning level policy
        warning_policy = {
            "name": "warning_test",
            "type": "resource_limits",
            "description": "Test warning policy",
            "level": "warning",
            "rules": [{"field": "cores", "max": 4}],
        }
        with open(policy_dir / "warning.yaml", "w") as f:
            yaml.dump(warning_policy, f)

        engine = PolicyEngine(policy_dir)
        resource = ResourceConfig(
            provider="test",
            type="vm",
            name="vm-01",
            config={"cores": 8}
        )
        violations = engine.evaluate_resources([resource], "dev")

        if violations:
            assert violations[0].level == PolicyLevel.WARNING

    def test_empty_policy_directory(self, temp_dir):
        """Test with empty policy directory."""
        empty_dir = temp_dir / "empty_policies"
        empty_dir.mkdir()

        engine = PolicyEngine(empty_dir)
        assert len(engine.policies) == 0

        # No policies = no violations
        resource = ResourceConfig(
            provider="test",
            type="vm",
            name="anything",
            config={}
        )
        violations = engine.evaluate_resources([resource], "dev")
        assert len(violations) == 0

    def test_evaluate_resources_multiple(self, mock_policy_dir):
        """Test evaluating multiple resources."""
        engine = PolicyEngine(mock_policy_dir)

        resources = [
            ResourceConfig(
                provider="proxmox",
                type="vm",
                name="vm-01",
                config={"cores": 2, "memory": 4096}
            ),
            ResourceConfig(
                provider="proxmox",
                type="vm",
                name="vm-02",
                config={"cores": 32, "memory": 8192}  # Violates cores limit
            ),
        ]

        all_violations = engine.evaluate_resources(resources, "dev")
        assert len(all_violations) > 0
        # Should have violations for vm-02
        assert any("vm-02" in v.resource_name for v in all_violations)

    def test_policy_violation_object(self):
        """Test PolicyViolation object."""
        violation = PolicyViolation(
            policy_name="test_policy",
            policy_type=PolicyType.RESOURCE_LIMIT,
            level=PolicyLevel.ERROR,
            resource_name="vm-01",
            provider="proxmox",
            message="Test violation",
        )
        assert violation.policy_name == "test_policy"
        assert violation.level == PolicyLevel.ERROR
        assert violation.resource_name == "vm-01"
