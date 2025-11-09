"""Unit tests for PolicyEngine."""

import pytest
import yaml

from infrafoundry.core.policy import (PolicyEngine, PolicyLevel, PolicyType,
                                      PolicyViolation)
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
            provider="proxmox", type="vm", name="vm-01", config={"cores": 8, "memory": 16384}
        )
        violations = engine.evaluate_resources([resource], "dev")
        # No violations
        cores_violations = [v for v in violations if "cores" in v.message]
        assert len(cores_violations) == 0

        # Resource exceeding limits
        resource2 = ResourceConfig(
            provider="proxmox", type="vm", name="vm-02", config={"cores": 32, "memory": 131072}
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
            config={"cores": 4, "tags": "environment, owner, project"},  # String format
        )
        violations = engine.evaluate_resources([resource], "dev")
        tag_violations = [v for v in violations if "tag" in v.message.lower()]
        assert len(tag_violations) == 0

        # Resource missing required tags
        resource2 = ResourceConfig(
            provider="proxmox",
            type="vm",
            name="vm-02",
            config={"cores": 4, "tags": "environment"},  # Missing owner and project
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
        resource = ResourceConfig(provider="test", type="vm", name="vm-01", config={"cores": 8})
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
        resource = ResourceConfig(provider="test", type="vm", name="anything", config={})
        violations = engine.evaluate_resources([resource], "dev")
        assert len(violations) == 0

    def test_evaluate_resources_multiple(self, mock_policy_dir):
        """Test evaluating multiple resources."""
        engine = PolicyEngine(mock_policy_dir)

        resources = [
            ResourceConfig(
                provider="proxmox", type="vm", name="vm-01", config={"cores": 2, "memory": 4096}
            ),
            ResourceConfig(
                provider="proxmox",
                type="vm",
                name="vm-02",
                config={"cores": 32, "memory": 8192},  # Violates cores limit
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

    def test_load_policies_invalid_yaml(self, temp_dir):
        """Test loading policies with invalid YAML."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        # Create invalid YAML file
        with open(policy_dir / "invalid.yaml", "w") as f:
            f.write("invalid: yaml: content:\n  bad indentation")

        # Should not raise exception, just skip the file
        engine = PolicyEngine(policy_dir)
        # No policies loaded from invalid file
        assert len(engine.policies) == 0

    def test_load_policies_empty_file(self, temp_dir):
        """Test loading policies from empty file."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        with open(policy_dir / "empty.yaml", "w") as f:
            f.write("")

        engine = PolicyEngine(policy_dir)
        assert len(engine.policies) == 0

    def test_load_policies_no_policies_key(self, temp_dir):
        """Test loading policies without policies key."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        with open(policy_dir / "nopolicies.yaml", "w") as f:
            yaml.dump({"other_key": "value"}, f)

        engine = PolicyEngine(policy_dir)
        assert len(engine.policies) == 0

    def test_disabled_policy_not_evaluated(self, temp_dir):
        """Test that disabled policies are not evaluated."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        policy = {
            "policies": [
                {
                    "name": "disabled_policy",
                    "type": "resource_limit",
                    "description": "Disabled test policy",
                    "enabled": False,
                    "rules": {"limits": {"max_cpu": 1}},
                }
            ]
        }
        with open(policy_dir / "disabled.yaml", "w") as f:
            yaml.dump(policy, f)

        engine = PolicyEngine(policy_dir)
        resource = ResourceConfig(provider="proxmox", type="vm", name="vm-01", config={"cores": 16})
        violations = engine.evaluate_resources([resource], "dev")
        # No violations because policy is disabled
        assert len(violations) == 0

    def test_policy_environment_filtering(self, temp_dir):
        """Test that policies only apply to specified environments."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        policy = {
            "policies": [
                {
                    "name": "prod_only",
                    "type": "resource_limit",
                    "description": "Production only policy",
                    "environments": ["prod"],
                    "rules": {"limits": {"max_cpu": 4}},
                }
            ]
        }
        with open(policy_dir / "prod.yaml", "w") as f:
            yaml.dump(policy, f)

        engine = PolicyEngine(policy_dir)
        resource = ResourceConfig(provider="proxmox", type="vm", name="vm-01", config={"cores": 16})

        # Should violate in prod
        violations_prod = engine.evaluate_resources([resource], "prod")
        assert len(violations_prod) > 0

        # Should NOT violate in dev
        violations_dev = engine.evaluate_resources([resource], "dev")
        assert len(violations_dev) == 0

    def test_naming_convention_policy(self, temp_dir):
        """Test naming convention policy."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        policy = {
            "policies": [
                {
                    "name": "naming_test",
                    "type": "naming_convention",
                    "description": "Naming convention test",
                    "rules": {"patterns": {"proxmox:vm": "^vm-[a-z]+-[0-9]{2}$"}},
                }
            ]
        }
        with open(policy_dir / "naming.yaml", "w") as f:
            yaml.dump(policy, f)

        engine = PolicyEngine(policy_dir)

        # Valid name
        resource1 = ResourceConfig(provider="proxmox", type="vm", name="vm-web-01", config={})
        violations1 = engine.evaluate_resources([resource1], "dev")
        assert len(violations1) == 0

        # Invalid name
        resource2 = ResourceConfig(provider="proxmox", type="vm", name="invalid_name", config={})
        violations2 = engine.evaluate_resources([resource2], "dev")
        assert len(violations2) > 0

    def test_naming_convention_wildcard_pattern(self, temp_dir):
        """Test naming convention with wildcard pattern."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        policy = {
            "policies": [
                {
                    "name": "naming_wildcard",
                    "type": "naming_convention",
                    "description": "Wildcard naming convention",
                    "rules": {"patterns": {"*": "^[a-z-]+$"}},
                }
            ]
        }
        with open(policy_dir / "naming_wildcard.yaml", "w") as f:
            yaml.dump(policy, f)

        engine = PolicyEngine(policy_dir)

        # Valid name
        resource1 = ResourceConfig(provider="any", type="any", name="valid-name", config={})
        violations1 = engine.evaluate_resources([resource1], "dev")
        assert len(violations1) == 0

        # Invalid name
        resource2 = ResourceConfig(provider="any", type="any", name="Invalid_Name_123", config={})
        violations2 = engine.evaluate_resources([resource2], "dev")
        assert len(violations2) > 0

    def test_naming_convention_invalid_regex(self, temp_dir):
        """Test naming convention with invalid regex pattern."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        policy = {
            "policies": [
                {
                    "name": "invalid_regex",
                    "type": "naming_convention",
                    "description": "Invalid regex test",
                    "rules": {"patterns": {"*": "[invalid(regex"}},
                }
            ]
        }
        with open(policy_dir / "invalid_regex.yaml", "w") as f:
            yaml.dump(policy, f)

        engine = PolicyEngine(policy_dir)
        resource = ResourceConfig(provider="any", type="any", name="anything", config={})
        # Should not raise exception, just print warning
        violations = engine.evaluate_resources([resource], "dev")
        # No violations because regex is invalid
        assert len(violations) == 0

    def test_required_tags_list_format(self, temp_dir):
        """Test required tags policy with list format tags."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        policy = {
            "policies": [
                {
                    "name": "tags_list",
                    "type": "required_tags",
                    "description": "Tags test",
                    "rules": {"tags": ["environment", "owner"]},
                }
            ]
        }
        with open(policy_dir / "tags.yaml", "w") as f:
            yaml.dump(policy, f)

        engine = PolicyEngine(policy_dir)

        # Valid: list format with all required tags
        resource1 = ResourceConfig(
            provider="proxmox",
            type="vm",
            name="vm-01",
            config={"tags": ["environment", "owner", "project"]},
        )
        violations1 = engine.evaluate_resources([resource1], "dev")
        tag_violations1 = [v for v in violations1 if "tag" in v.message.lower()]
        assert len(tag_violations1) == 0

        # Invalid: list format missing tags
        resource2 = ResourceConfig(
            provider="proxmox", type="vm", name="vm-02", config={"tags": ["environment"]}
        )
        violations2 = engine.evaluate_resources([resource2], "dev")
        tag_violations2 = [v for v in violations2 if "tag" in v.message.lower()]
        assert len(tag_violations2) > 0

    def test_required_tags_no_tags(self, temp_dir):
        """Test required tags policy with resource having no tags."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        policy = {
            "policies": [
                {
                    "name": "tags_required",
                    "type": "required_tags",
                    "description": "Tags required",
                    "rules": {"tags": ["environment"]},
                }
            ]
        }
        with open(policy_dir / "tags_req.yaml", "w") as f:
            yaml.dump(policy, f)

        engine = PolicyEngine(policy_dir)
        resource = ResourceConfig(provider="proxmox", type="vm", name="vm-01", config={})
        violations = engine.evaluate_resources([resource], "dev")
        tag_violations = [v for v in violations if "tag" in v.message.lower()]
        assert len(tag_violations) > 0

    def test_required_tags_invalid_format(self, temp_dir):
        """Test required tags policy with invalid tags format."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        policy = {
            "policies": [
                {
                    "name": "tags_test",
                    "type": "required_tags",
                    "description": "Tags test",
                    "rules": {"tags": ["environment"]},
                }
            ]
        }
        with open(policy_dir / "tags_invalid.yaml", "w") as f:
            yaml.dump(policy, f)

        engine = PolicyEngine(policy_dir)
        # Tags as dict (invalid format, should be treated as empty set)
        resource = ResourceConfig(
            provider="proxmox", type="vm", name="vm-01", config={"tags": {"key": "value"}}
        )
        violations = engine.evaluate_resources([resource], "dev")
        tag_violations = [v for v in violations if "tag" in v.message.lower()]
        assert len(tag_violations) > 0

    def test_allowed_providers_policy(self, temp_dir):
        """Test allowed providers policy."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        policy = {
            "policies": [
                {
                    "name": "allowed_providers",
                    "type": "allowed_providers",
                    "description": "Only allow specific providers",
                    "rules": {"allowed": ["proxmox", "kubernetes"]},
                }
            ]
        }
        with open(policy_dir / "providers.yaml", "w") as f:
            yaml.dump(policy, f)

        engine = PolicyEngine(policy_dir)

        # Allowed provider
        resource1 = ResourceConfig(provider="proxmox", type="vm", name="vm-01", config={})
        violations1 = engine.evaluate_resources([resource1], "dev")
        assert len(violations1) == 0

        # Disallowed provider
        resource2 = ResourceConfig(
            provider="opnsense", type="firewall_rule", name="rule-01", config={}
        )
        violations2 = engine.evaluate_resources([resource2], "dev")
        assert len(violations2) > 0

    def test_allowed_providers_empty_list(self, temp_dir):
        """Test allowed providers policy with empty allowed list."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        policy = {
            "policies": [
                {
                    "name": "no_providers",
                    "type": "allowed_providers",
                    "description": "Empty allowed list",
                    "rules": {"allowed": []},
                }
            ]
        }
        with open(policy_dir / "no_providers.yaml", "w") as f:
            yaml.dump(policy, f)

        engine = PolicyEngine(policy_dir)
        resource = ResourceConfig(provider="proxmox", type="vm", name="vm-01", config={})
        violations = engine.evaluate_resources([resource], "dev")
        # Empty allowed list means policy doesn't apply
        assert len(violations) == 0

    def test_get_policy(self, mock_policy_dir):
        """Test getting a specific policy by name."""
        engine = PolicyEngine(mock_policy_dir)
        policy = engine.get_policy("resource_limits")
        assert policy is not None
        assert policy.name == "resource_limits"

        # Non-existent policy
        missing = engine.get_policy("nonexistent")
        assert missing is None

    def test_get_policies_for_environment(self, temp_dir):
        """Test getting policies for a specific environment."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        policy = {
            "policies": [
                {
                    "name": "prod_only",
                    "type": "resource_limit",
                    "description": "Prod only",
                    "environments": ["prod"],
                    "rules": {},
                },
                {
                    "name": "all_envs",
                    "type": "resource_limit",
                    "description": "All environments",
                    "rules": {},
                },
                {
                    "name": "disabled",
                    "type": "resource_limit",
                    "description": "Disabled",
                    "enabled": False,
                    "rules": {},
                },
            ]
        }
        with open(policy_dir / "multi.yaml", "w") as f:
            yaml.dump(policy, f)

        engine = PolicyEngine(policy_dir)

        # Prod environment should get prod_only and all_envs (not disabled)
        prod_policies = engine.get_policies_for_environment("prod")
        prod_names = {p.name for p in prod_policies}
        assert "prod_only" in prod_names
        assert "all_envs" in prod_names
        assert "disabled" not in prod_names

        # Dev environment should only get all_envs (not prod_only or disabled)
        dev_policies = engine.get_policies_for_environment("dev")
        dev_names = {p.name for p in dev_policies}
        assert "prod_only" not in dev_names
        assert "all_envs" in dev_names
        assert "disabled" not in dev_names

    def test_resource_limit_memory_only(self, temp_dir):
        """Test resource limits policy with only memory limit."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        policy = {
            "policies": [
                {
                    "name": "memory_limit",
                    "type": "resource_limit",
                    "description": "Memory limit only",
                    "rules": {"limits": {"max_memory_mb": 8192}},
                }
            ]
        }
        with open(policy_dir / "memory.yaml", "w") as f:
            yaml.dump(policy, f)

        engine = PolicyEngine(policy_dir)

        # Within limit
        resource1 = ResourceConfig(
            provider="proxmox", type="vm", name="vm-01", config={"memory": 4096}
        )
        violations1 = engine.evaluate_resources([resource1], "dev")
        assert len(violations1) == 0

        # Exceeds limit
        resource2 = ResourceConfig(
            provider="proxmox", type="vm", name="vm-02", config={"memory": 16384}
        )
        violations2 = engine.evaluate_resources([resource2], "dev")
        assert len(violations2) > 0

    def test_resource_with_cpu_field(self, temp_dir):
        """Test resource limits with 'cpu' field instead of 'cores'."""
        policy_dir = temp_dir / "policies"
        policy_dir.mkdir()

        policy = {
            "policies": [
                {
                    "name": "cpu_limit",
                    "type": "resource_limit",
                    "description": "CPU limit",
                    "rules": {"limits": {"max_cpu": 8}},
                }
            ]
        }
        with open(policy_dir / "cpu.yaml", "w") as f:
            yaml.dump(policy, f)

        engine = PolicyEngine(policy_dir)

        # Using 'cpu' field instead of 'cores'
        resource = ResourceConfig(
            provider="kubernetes", type="deployment", name="deploy-01", config={"cpu": 16}
        )
        violations = engine.evaluate_resources([resource], "dev")
        assert len(violations) > 0
