"""Unit tests for BlueprintValidator."""

from pathlib import Path

import pytest

from infrafoundry.core.config.blueprint_resolver import BlueprintResolver
from infrafoundry.core.config.blueprint_validator import (
    BlueprintValidationResult,
    BlueprintValidator,
    ProviderValidationResult,
)


def _write_template(directory: Path, filename: str, content: str) -> None:
    """Write a template file, creating parent directories as needed."""
    path = directory / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _make_resolved(
    tmp_path: Path,
    name: str = "test-bp",
    defaults: dict | None = None,
    resources: list[str] | None = None,
    providers: dict | None = None,
) -> dict:
    """Build a resolved-blueprint dict suitable for BlueprintValidator."""
    result: dict = {
        "name": name,
        "description": "test blueprint",
        "version": "1.0.0",
        "defaults": defaults or {},
        "resources": resources or [],
        "events": {},
        "inventory": None,
        "inventory_raw": None,
        "blueprint_dir": tmp_path,
        "providers": providers,
    }
    return result


# ------------------------------------------------------------------
# Dataclass / property tests
# ------------------------------------------------------------------


@pytest.mark.unit
class TestProviderValidationResult:
    """Tests for ProviderValidationResult dataclass."""

    def test_default_fields(self):
        """Default fields are empty."""
        r = ProviderValidationResult(provider="test")
        assert r.provider == "test"
        assert r.template_vars == frozenset()
        assert r.defaults == frozenset()
        assert r.errors == []
        assert r.warnings == []


@pytest.mark.unit
class TestBlueprintValidationResult:
    """Tests for BlueprintValidationResult dataclass."""

    def test_has_errors_false_when_clean(self):
        """has_errors is False when no provider has errors."""
        r = BlueprintValidationResult(
            blueprint_name="bp",
            is_multi_provider=False,
            providers=[ProviderValidationResult(provider="default")],
        )
        assert r.has_errors is False

    def test_has_errors_true(self):
        """has_errors is True when a provider has errors."""
        r = BlueprintValidationResult(
            blueprint_name="bp",
            is_multi_provider=False,
            providers=[
                ProviderValidationResult(provider="default", errors=["Undefined variable: 'x'"])
            ],
        )
        assert r.has_errors is True

    def test_has_warnings_true(self):
        """has_warnings is True when a provider has warnings."""
        r = BlueprintValidationResult(
            blueprint_name="bp",
            is_multi_provider=True,
            providers=[
                ProviderValidationResult(provider="oci", warnings=["Asymmetric variable: 'foo'"])
            ],
        )
        assert r.has_warnings is True


# ------------------------------------------------------------------
# Single-provider tests
# ------------------------------------------------------------------


@pytest.mark.unit
class TestSingleProviderValidation:
    """Tests for single-provider blueprint validation."""

    def test_clean_single_provider(self, tmp_path):
        """All template vars covered by defaults produces no errors."""
        _write_template(tmp_path, "vm.yaml", "name: {{ vm_name }}\ncores: {{ cores }}")
        resolved = _make_resolved(
            tmp_path,
            defaults={"vm_name": "test", "cores": 2},
            resources=["vm.yaml"],
        )
        result = BlueprintValidator(resolved).validate()
        assert not result.has_errors
        assert not result.has_warnings
        assert result.is_multi_provider is False
        assert result.providers[0].provider == "default"

    def test_missing_vars_produces_errors(self, tmp_path):
        """Template vars not in defaults produce errors."""
        _write_template(tmp_path, "vm.yaml", "name: {{ vm_name }}\nip: {{ ip_address }}")
        resolved = _make_resolved(
            tmp_path,
            defaults={"vm_name": "test"},
            resources=["vm.yaml"],
        )
        result = BlueprintValidator(resolved).validate()
        assert result.has_errors
        assert len(result.providers[0].errors) == 1
        assert "ip_address" in result.providers[0].errors[0]

    def test_for_loop_vars_excluded(self, tmp_path):
        """Variables bound by for loops are not reported as undeclared."""
        template = "{% for item in items %}\n  name: {{ item.name }}\n{% endfor %}\n"
        _write_template(tmp_path, "loop.yaml", template)
        resolved = _make_resolved(
            tmp_path,
            defaults={"items": []},
            resources=["loop.yaml"],
        )
        result = BlueprintValidator(resolved).validate()
        assert not result.has_errors
        # 'item' should not appear as undeclared
        assert "item" not in result.providers[0].template_vars


# ------------------------------------------------------------------
# Multi-provider tests
# ------------------------------------------------------------------


@pytest.mark.unit
class TestMultiProviderValidation:
    """Tests for multi-provider blueprint validation."""

    def test_clean_multi_provider(self, tmp_path):
        """All vars covered produces no errors or warnings."""
        _write_template(
            tmp_path, "providers/a/vm.yaml", "name: {{ cluster_name }}\ncpu: {{ cores }}"
        )
        _write_template(
            tmp_path, "providers/b/vm.yaml", "name: {{ cluster_name }}\nmem: {{ memory }}"
        )
        resolved = _make_resolved(
            tmp_path,
            defaults={"cluster_name": "test"},
            providers={
                "a": {
                    "defaults": {"cores": 2},
                    "resources": ["providers/a/vm.yaml"],
                },
                "b": {
                    "defaults": {"memory": 4096},
                    "resources": ["providers/b/vm.yaml"],
                },
            },
        )
        result = BlueprintValidator(resolved).validate()
        assert not result.has_errors
        assert not result.has_warnings
        assert result.is_multi_provider is True

    def test_asymmetric_warning(self, tmp_path):
        """Global default used by one provider but not another produces warning."""
        _write_template(
            tmp_path, "providers/a/vm.yaml", "name: {{ cluster_name }}\ncpu: {{ shared_var }}"
        )
        _write_template(tmp_path, "providers/b/vm.yaml", "name: {{ cluster_name }}")
        resolved = _make_resolved(
            tmp_path,
            defaults={"cluster_name": "test", "shared_var": "val"},
            providers={
                "a": {
                    "defaults": {},
                    "resources": ["providers/a/vm.yaml"],
                },
                "b": {
                    "defaults": {},
                    "resources": ["providers/b/vm.yaml"],
                },
            },
        )
        result = BlueprintValidator(resolved).validate()
        assert not result.has_errors
        assert result.has_warnings
        # Provider b should have the asymmetry warning
        b_result = next(p for p in result.providers if p.provider == "b")
        assert any("shared_var" in w for w in b_result.warnings)

    def test_undefined_error_multi_provider(self, tmp_path):
        """Variable not in any defaults layer produces error in multi-provider."""
        _write_template(tmp_path, "providers/a/vm.yaml", "ip: {{ ip_address }}")
        resolved = _make_resolved(
            tmp_path,
            defaults={},
            providers={
                "a": {
                    "defaults": {},
                    "resources": ["providers/a/vm.yaml"],
                },
            },
        )
        result = BlueprintValidator(resolved).validate()
        assert result.has_errors
        a_result = result.providers[0]
        assert any("ip_address" in e for e in a_result.errors)


# ------------------------------------------------------------------
# Custom filter tests
# ------------------------------------------------------------------


@pytest.mark.unit
class TestCustomFilters:
    """Tests for custom Jinja2 filter handling."""

    def test_generate_mac_filter_no_parse_error(self, tmp_path):
        """Templates using generate_mac filter parse without error."""
        _write_template(
            tmp_path,
            "vm.yaml",
            'macaddr: "{{ vm_name | generate_mac }}"',
        )
        resolved = _make_resolved(
            tmp_path,
            defaults={"vm_name": "test"},
            resources=["vm.yaml"],
        )
        result = BlueprintValidator(resolved).validate()
        assert not result.has_errors


# ------------------------------------------------------------------
# Real blueprint integration tests
# ------------------------------------------------------------------


@pytest.mark.unit
class TestRealBlueprints:
    """Tests against real blueprints in the repository."""

    @staticmethod
    def _get_real_resolver() -> BlueprintResolver:
        """Get a resolver that finds real framework blueprints."""
        return BlueprintResolver(base_dir=Path("."))

    def test_aiqum_blueprint_no_errors(self):
        """Real aiqum blueprint should have zero validation errors.

        The aiqum blueprint is single-provider and all template vars
        should be covered by defaults (except per-instance vars like
        vm_name, vmid, target_node, etc. supplied by packages).
        """
        resolver = self._get_real_resolver()
        if not resolver.exists("aiqum"):
            pytest.skip("aiqum blueprint not available")

        resolved = resolver.resolve("aiqum")
        result = BlueprintValidator(resolved).validate()

        # Document expected undefined vars (per-instance, supplied by packages)
        assert not result.is_multi_provider
        # These should NOT be errors — they are intentional.
        # But since they're per-instance vars not in defaults, they will
        # be reported. This test documents the expected behaviour.
        prov = result.providers[0]
        expected_undefined = {
            "vm_name",
            "vmid",
            "target_node",
            "disk_storage",
            "ip_address",
            "dhcp_subnet",
        }
        actual_undefined_vars = {e.split("'")[1] for e in prov.errors if "Undefined variable" in e}
        # All actual undefined vars should be in the expected set
        assert actual_undefined_vars == expected_undefined

    def test_k3s_cluster_blueprint_validation(self):
        """Real k3s-cluster blueprint documents expected undefined vars.

        The k3s-cluster blueprint is multi-provider. Per-instance variables
        (server_name, agents, image, etc.) are supplied by packages and
        will appear as undefined in static analysis.
        """
        resolver = self._get_real_resolver()
        if not resolver.exists("k3s-cluster"):
            pytest.skip("k3s-cluster blueprint not available")

        resolved = resolver.resolve("k3s-cluster")
        result = BlueprintValidator(resolved).validate()

        assert result.is_multi_provider
        assert len(result.providers) == 2

        # Both providers will have undefined vars (per-instance values)
        proxmox = next(p for p in result.providers if p.provider == "proxmox")
        oci = next(p for p in result.providers if p.provider == "oci")

        # Proxmox should reference per-instance vars not in defaults
        proxmox_undefined = {e.split("'")[1] for e in proxmox.errors if "Undefined variable" in e}
        assert "server_name" in proxmox_undefined
        assert "agents" in proxmox_undefined

        # OCI should reference per-instance vars not in defaults
        oci_undefined = {e.split("'")[1] for e in oci.errors if "Undefined variable" in e}
        assert "image" in oci_undefined
        assert "ssh_public_key" in oci_undefined
