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
# inputs:-schema tests
# ------------------------------------------------------------------


@pytest.mark.unit
class TestInputsSchemaValidation:
    """Tests covering the new ``input_names``-based validation path."""

    def test_required_input_without_default_is_accepted(self, tmp_path):
        """A declared input without a ``default:`` is not flagged as undefined."""
        _write_template(tmp_path, "vm.yaml", "name: {{ vm_name }}\ncores: {{ cores }}")
        resolved = _make_resolved(
            tmp_path,
            defaults={"cores": 2},  # only defaults-backed
            resources=["vm.yaml"],
        )
        # The resolver normally populates ``input_names``; simulate that here.
        resolved["input_names"] = frozenset({"vm_name", "cores"})
        result = BlueprintValidator(resolved).validate()
        assert not result.has_errors

    def test_truly_undefined_variable_is_still_flagged(self, tmp_path):
        """Typos / vars not declared as inputs must still error."""
        _write_template(tmp_path, "vm.yaml", "name: {{ vm_nmae }}")
        resolved = _make_resolved(tmp_path, defaults={}, resources=["vm.yaml"])
        resolved["input_names"] = frozenset({"vm_name"})
        result = BlueprintValidator(resolved).validate()
        assert result.has_errors
        # New error message wording.
        assert any("not declared in inputs" in e for e in result.providers[0].errors)

    def test_provider_scoped_input_not_visible_to_sibling(self, tmp_path):
        """A variable declared only for provider A is undefined for provider B."""
        _write_template(tmp_path, "providers/a/vm.yaml", "name: {{ only_in_a }}")
        _write_template(tmp_path, "providers/b/vm.yaml", "name: {{ only_in_a }}")
        resolved = _make_resolved(
            tmp_path,
            defaults={},
            providers={
                "a": {
                    "defaults": {},
                    "input_names": frozenset({"only_in_a"}),
                    "resources": ["providers/a/vm.yaml"],
                },
                "b": {
                    "defaults": {},
                    "input_names": frozenset(),
                    "resources": ["providers/b/vm.yaml"],
                },
            },
        )
        resolved["input_names"] = frozenset()
        result = BlueprintValidator(resolved).validate()
        a_result = next(p for p in result.providers if p.provider == "a")
        b_result = next(p for p in result.providers if p.provider == "b")
        assert a_result.errors == []
        assert any("only_in_a" in e for e in b_result.errors)


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

        All template variables (including per-instance ones like ``vm_name``,
        ``vmid``, ``target_node``) are now declared in the blueprint's
        ``inputs:`` section, so static analysis should report no undefined
        variables.
        """
        resolver = self._get_real_resolver()
        if not resolver.exists("aiqum"):
            pytest.skip("aiqum blueprint not available")

        resolved = resolver.resolve("aiqum")
        result = BlueprintValidator(resolved).validate()

        assert not result.is_multi_provider
        prov = result.providers[0]
        assert prov.errors == [], f"Unexpected undefined variables: {prov.errors}"
        # Required per-instance inputs should appear in the declared set.
        for required in ("vm_name", "vmid", "target_node", "ip_address", "dhcp_subnet"):
            assert required in prov.defaults

    def test_k3s_cluster_blueprint_validation(self):
        """Real k3s-cluster blueprint validates cleanly post-migration.

        Top-level and per-provider ``inputs:`` should cover every template
        variable, producing no undefined-variable errors.
        """
        resolver = self._get_real_resolver()
        if not resolver.exists("k3s-cluster"):
            pytest.skip("k3s-cluster blueprint not available")

        resolved = resolver.resolve("k3s-cluster")
        result = BlueprintValidator(resolved).validate()

        assert result.is_multi_provider
        assert len(result.providers) == 2

        proxmox = next(p for p in result.providers if p.provider == "proxmox")
        oci = next(p for p in result.providers if p.provider == "oci")

        assert proxmox.errors == [], f"proxmox errors: {proxmox.errors}"
        assert oci.errors == [], f"oci errors: {oci.errors}"

        # Proxmox-scoped required inputs should be declared for that provider.
        for required in ("server_name", "agents", "server_mac", "server_ip"):
            assert required in proxmox.defaults

        # OCI-scoped required inputs should be declared for that provider.
        for required in ("image", "ssh_public_key"):
            assert required in oci.defaults

    def test_all_real_blueprints_validate(self):
        """Every blueprint shipped in the framework should validate cleanly."""
        resolver = self._get_real_resolver()
        for name in resolver.list_blueprints():
            resolved = resolver.resolve(name)
            result = BlueprintValidator(resolved).validate()
            for provider in result.providers:
                assert provider.errors == [], (
                    f"Blueprint '{name}' provider '{provider.provider}' has "
                    f"undefined variables: {provider.errors}"
                )
