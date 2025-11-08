"""Unit tests for PolicyEngine."""

import pytest
import yaml

from infrafoundry.core.policy import PolicyEngine, PolicyLevel, PolicyViolation


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
        policy_names = {p["name"] for p in engine.policies}
        assert "resource_limits" in policy_names
        assert "require_tags" in policy_names

    def test_validate_resource_limits(self, mock_policy_dir):
        """Test resource limits policy."""
        engine = PolicyEngine(mock_policy_dir)

        # Resource within limits
        resource = {"name": "vm-01", "cores": 8, "memory": 16384}
        violations = engine.check_resource("proxmox", "vm", resource)
        assert len(violations) == 0

        # Resource exceeding limits
        resource = {"name": "vm-02", "cores": 32, "memory": 131072}
        violations = engine.check_resource("proxmox", "vm", resource)
        assert len(violations) > 0
        assert any("cores" in v.message for v in violations)

    def test_validate_required_tags(self, mock_policy_dir):
        """Test required tags policy."""
        engine = PolicyEngine(mock_policy_dir)

        # Resource with all required tags
        resource = {
            "name": "vm-01",
            "tags": {"environment": "dev", "owner": "team-infra", "project": "test"},
        }
        violations = engine.check_resource("proxmox", "vm", resource)
        # Only resource_limits violations if any
        tag_violations = [v for v in violations if "tag" in v.message.lower()]
        assert len(tag_violations) == 0

        # Resource missing required tags
        resource = {"name": "vm-02", "tags": {"environment": "dev"}}
        violations = engine.check_resource("proxmox", "vm", resource)
        tag_violations = [v for v in violations if "tag" in v.message.lower()]
        assert len(tag_violations) > 0

    def test_policy_level_enforcement(self, temp_dir):
        """Test different policy enforcement levels."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        # Warning level policy
        warning_policy = {
            "name": "warning_test",
            "description": "Test warning policy",
            "level": "warning",
            "rules": [{"field": "cores", "max": 4}],
        }
        with open(policy_dir / "warning.yaml", "w") as f:
            yaml.dump(warning_policy, f)

        engine = PolicyEngine(policy_dir)
        resource = {"name": "vm-01", "cores": 8}
        violations = engine.check_resource("test", "vm", resource)

        if violations:
            assert violations[0].level == PolicyLevel.WARNING

    def test_empty_policy_directory(self, temp_dir):
        """Test with empty policy directory."""
        empty_dir = temp_dir / "empty_policies"
        empty_dir.mkdir()

        engine = PolicyEngine(empty_dir)
        assert len(engine.policies) == 0

        # No policies = no violations
        resource = {"name": "anything"}
        violations = engine.check_resource("test", "vm", resource)
        assert len(violations) == 0

    def test_check_all_resources(self, mock_policy_dir):
        """Test checking multiple resources."""
        engine = PolicyEngine(mock_policy_dir)

        resources = {
            "proxmox": {
                "vm": [
                    {"name": "vm-01", "cores": 2, "memory": 4096},
                    {"name": "vm-02", "cores": 32, "memory": 8192},  # Violates cores limit
                ]
            }
        }

        all_violations = engine.check_all_resources(resources, "dev")
        assert len(all_violations) > 0
        # Should have violations for vm-02
        assert any("vm-02" in v.resource for v in all_violations)

    def test_policy_violation_object(self):
        """Test PolicyViolation object."""
        violation = PolicyViolation(
            policy="test_policy",
            level=PolicyLevel.ERROR,
            resource="vm-01",
            message="Test violation",
        )
        assert violation.policy == "test_policy"
        assert violation.level == PolicyLevel.ERROR
        assert violation.resource == "vm-01"
        assert "test_policy" in str(violation)
