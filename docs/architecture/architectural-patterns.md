# Architectural Patterns Documentation

## Manager Pattern Standardization

All manager classes now inherit from `BaseManager` to ensure consistent behavior across the codebase.

### BaseManager

Located in: `src/infrafoundry/core/base_manager.py`

**Provides:**
- Standard logging interface (`_log_info`, `_log_warning`, `_log_error`, `_log_debug`)
- Error handling pattern (`_handle_error`)
- Context manager support (`__enter__`, `__exit__`)
- Abstract `cleanup()` method for resource cleanup

**Usage:**
```python
from infrafoundry.core.base_manager import BaseManager

class MyManager(BaseManager):
    def __init__(self, config_path: Path):
        super().__init__()  # Sets up logging
        self.config_path = config_path
        self._log_info("Manager initialized", path=str(config_path))

    def do_work(self):
        try:
            # Do work
            self._log_debug("Processing...")
        except Exception as e:
            self._handle_error("Work failed", e, raise_error=True)

    def cleanup(self) -> None:
        # Clean up resources
        self._log_info("Cleaned up")
```

**Context Manager Support:**
```python
with MyManager(config_path) as manager:
    manager.do_work()
# cleanup() called automatically
```

### PathBasedManager

Located in: `src/infrafoundry/core/base_manager.py`

Extends `BaseManager` for managers that work with filesystem paths.

**Provides:**
- Path resolution with environment variable support (`_resolve_path`)
- Directory creation (`_ensure_directory_exists`)
- Path validation (`_validate_path_exists`)
- Environment variable helper (`_get_env_var`)

**Usage:**
```python
from infrafoundry.core.base_manager import PathBasedManager

class ConfigManager(PathBasedManager):
    def __init__(self, base_dir: Path | None = None):
        super().__init__()
        if base_dir is None:
            config_repo = self._get_env_var("INFRAFOUNDRY_CONFIG_REPO")
            if not config_repo:
                raise ValueError("INFRAFOUNDRY_CONFIG_REPO must be set")
            base_dir = Path(config_repo) / "envs"
        self.base_dir = base_dir
```

## Provider Mixin Pattern

Common provider functionality extracted into mixins to reduce code duplication.

### TemplateRendererMixin

Located in: `src/infrafoundry/core/provider_mixins.py`

**Provides:**
- Jinja2 environment setup with sensible defaults
- Template loading and rendering
- Common template filters (to_terraform_name, to_snake_case, to_kebab_case)
- Helper methods for writing files

**Usage:**
```python
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.provider_mixins import TemplateRendererMixin

class MyProvider(ProviderBase, TemplateRendererMixin):
    def __init__(self, config_dir: Path, output_dir: Path):
        super().__init__("myprovider", config_dir, output_dir)
        self._setup_template_environment()  # From mixin

    def generate_terraform(self, resources):
        self.ensure_directories()

        # Use mixin methods
        template = self.get_template("myprovider/main.tf.j2")
        content = template.render(resources=resources)
        self._write_terraform_file("main.tf", content)
```

**Available Template Filters:**
- `to_terraform_name`: Convert `my-resource` → `my_resource`
- `to_snake_case`: Convert `My Resource` → `my_resource`
- `to_kebab_case`: Convert `my_resource` → `my-resource`
- `quote`: Wrap string in quotes

### ResourceGrouperMixin

Located in: `src/infrafoundry/core/provider_mixins.py`

**Provides:**
- Resource grouping by type
- Resource type validation
- Resource counting and filtering

**Usage:**
```python
from infrafoundry.core.provider import ProviderBase
from infrafoundry.core.provider_mixins import ResourceGrouperMixin

class MyProvider(ProviderBase, ResourceGrouperMixin):
    def generate_terraform(self, resources):
        # Group resources by type
        grouped = self.group_resources_by_type(resources)

        if "vm" in grouped:
            self._generate_vms(grouped["vm"])

        if "network" in grouped:
            self._generate_networks(grouped["network"])

    def validate_resources(self, resources):
        # Validate resource types
        valid, invalid = self.validate_resource_types(resources)

        if invalid:
            raise ValueError(f"Invalid resource types: {[r.type for r in invalid]}")
```

**Available Methods:**
- `group_resources_by_type(resources)` → Dict[str, List[ResourceConfig]]
- `validate_resource_types(resources, supported_types)` → Tuple[valid, invalid]
- `get_resource_names_by_type(resources, type)` → Set[str]
- `count_resources_by_type(resources)` → Dict[str, int]

## Combining Patterns

Providers can use both mixins together:

```python
class MyProvider(ProviderBase, TemplateRendererMixin, ResourceGrouperMixin):
    def __init__(self, config_dir: Path, output_dir: Path):
        super().__init__("myprovider", config_dir, output_dir)
        self._setup_template_environment()  # From TemplateRendererMixin

    def generate_terraform(self, resources):
        self.ensure_directories()

        # From ResourceGrouperMixin
        grouped = self.group_resources_by_type(resources)

        # From TemplateRendererMixin
        template = self.get_template("myprovider/main.tf.j2")
        content = template.render(resources=grouped)
        self._write_terraform_file("main.tf", content)
```

## Benefits

1. **Consistency**: All managers follow the same initialization and logging patterns
2. **Reusability**: Common functionality extracted to mixins
3. **Maintainability**: Changes to patterns done in one place
4. **Testability**: Mixins can be tested independently
5. **Documentation**: Patterns are self-documenting through base classes

## 3-Layer Architecture Pattern (OPNsense Provider)

The OPNsense provider implements a modern 3-layer architecture that separates concerns and improves testability:

### Layer 1: Service Layer (API Operations)

**Purpose:** Low-level API operations and data access

**Location:** `src/infrafoundry/providers/opnsense/services/`

**Pattern:**
```python
from ..api_client import OPNsenseClient
from .base import BaseService

class KeaDHCPService(BaseService):
    """Service for Kea DHCP operations via OPNsense API."""

    def __init__(self, client: OPNsenseClient):
        super().__init__(client)

    @classmethod
    def from_environment(
        cls, env_name: str, provider_name: str, config_dir: Path
    ) -> "KeaDHCPService":
        """Factory method to create service from environment settings."""
        # Load credentials, create client, return service

    def search_dhcpv4_subnets(self) -> list[dict]:
        """Low-level API call."""
        return self.client.request("GET", "kea/dhcpv4/searchSubnet")

    def delete_dhcpv4_subnet(self, uuid: str) -> dict:
        """Low-level API call."""
        return self.client.request("POST", f"kea/dhcpv4/delSubnet/{uuid}")
```

**Services:**
- `BaseService` - Abstract base with factory pattern
- `KeaDHCPService` - Kea DHCP API operations
- `ISCDHCPService` - ISC DHCP configuration reading

### Layer 2: Component Manager (Orchestration)

**Purpose:** Business logic and orchestration of multiple service calls

**Location:** `src/infrafoundry/providers/opnsense/components/`

**Pattern:**
```python
from ..services.kea_dhcp import KeaDHCPService
from .base import BaseComponentManager

class KeaDHCPManager(BaseComponentManager):
    """Manager for Kea DHCP operations."""

    def reset_dhcpv4(self, env_name: str, provider_name: str = "opnsense") -> None:
        """Orchestrate DHCPv4 reset (multiple API calls)."""
        service: KeaDHCPService = KeaDHCPService.from_environment(
            env_name, provider_name, self.config_dir
        )

        # Get all subnets
        subnets = service.search_dhcpv4_subnets()

        # Delete each subnet
        for subnet in subnets:
            service.delete_dhcpv4_subnet(subnet["uuid"])

        # Reconfigure service
        service.reconfigure_service()
```

**Managers:**
- `BaseComponentManager` - Base class for managers
- `KeaDHCPManager` - Kea DHCP reset/migrate operations
- `ISCToKeaMigrationManager` - ISC to Kea migration orchestration

### Layer 3: Provider (Delegation)

**Purpose:** Thin delegation layer that exposes operations to the framework

**Location:** `src/infrafoundry/providers/opnsense/__init__.py`

**Pattern:**
```python
class OPNsenseProvider(ProviderBase):
    """OPNsense provider - thin delegation layer."""

    def reset_kea_dhcpv4(self, env_name: str) -> None:
        """Reset Kea DHCPv4 configuration."""
        from .components.kea_dhcp import KeaDHCPManager

        manager = KeaDHCPManager(self.config_dir)
        manager.reset_dhcpv4(env_name, "opnsense")
```

**Benefits:**
- Provider stays thin (3-4 lines per method)
- Business logic isolated in managers
- API operations isolated in services
- Easy to test each layer independently
- Services reusable across managers

### Type Handling Pattern

When using factories that return base types but need concrete types:

```python
# Type ignore needed because factory returns base type
service: KeaDHCPService = KeaDHCPService.from_environment(  # type: ignore[assignment]
    env_name, provider_name, self.config_dir
)
```

This is correct - the factory method is defined in `BaseService` so it returns `BaseService`, but we know the actual type and need concrete methods.

### Testing Pattern

**Service Layer Tests:**
```python
def test_search_dhcpv4_subnets(mock_client):
    service = KeaDHCPService(mock_client)
    result = service.search_dhcpv4_subnets()
    mock_client.request.assert_called_once_with("GET", "kea/dhcpv4/searchSubnet")
```

**Component Manager Tests:**
```python
@patch('path.to.KeaDHCPService.from_environment')
def test_reset_dhcpv4(mock_service_factory):
    mock_service = MagicMock()
    mock_service.search_dhcpv4_subnets.return_value = [{"uuid": "123"}]
    mock_service_factory.return_value = mock_service

    manager = KeaDHCPManager(tmp_path)
    manager.reset_dhcpv4("dev", "opnsense")

    mock_service.delete_dhcpv4_subnet.assert_called_once_with("123")
```

**Provider Tests:**
```python
@patch('path.to.KeaDHCPManager')
def test_reset_kea_dhcpv4_delegates_to_manager(mock_manager_class):
    mock_manager = MagicMock()
    mock_manager_class.return_value = mock_manager

    provider = OPNsenseProvider(config_dir, output_dir)
    provider.reset_kea_dhcpv4("dev")

    mock_manager.reset_dhcpv4.assert_called_once_with("dev", "opnsense")
```

### When to Use This Pattern

**Use 3-layer architecture when:**
- Provider needs complex API operations (multiple calls, error handling)
- Operations need business logic beyond simple API calls
- Want to reuse API operations across different features
- Need detailed unit testing of business logic

**Keep provider simple when:**
- Operations are straightforward template rendering
- No complex API interactions
- Simple CRUD operations via Terraform

**Current Usage:**
- ✅ **OPNsense Provider**: Full 3-layer architecture for DHCP operations
- ⏭️ **Proxmox Provider**: Simple template-based (no complex API operations needed)
- ⏭️ **Kubernetes Provider**: Simple template-based (kubectl handles everything)

## Migration Guide

### For New Managers

1. Inherit from `BaseManager` or `PathBasedManager`
2. Call `super().__init__()` in your `__init__`
3. Implement `cleanup()` method
4. Use provided logging methods (`_log_info`, etc.)

### For New Providers

1. Inherit from `ProviderBase` plus mixins
2. Call `_setup_template_environment()` if using TemplateRendererMixin
3. Use `group_resources_by_type()` for resource organization
4. Use mixin methods for template rendering and file writing

### For 3-Layer Architecture

1. **Create Service** in `providers/{name}/services/`:
   - Inherit from `BaseService`
   - Implement low-level API operations
   - Add `from_environment()` factory if needed

2. **Create Component Manager** in `providers/{name}/components/`:
   - Inherit from `BaseComponentManager`
   - Orchestrate service calls
   - Implement business logic

3. **Add Provider Method**:
   - 3-line delegation to component manager
   - Let manager handle all logic

### Backward Compatibility

All existing code continues to work without changes. The patterns are additive and don't break existing functionality.

