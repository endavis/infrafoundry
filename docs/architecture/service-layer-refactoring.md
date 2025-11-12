# Architectural Refactoring: Service Layer + Component Managers

## Summary

Successfully refactored the OPNsense provider's reset and migrate functionality into a modular, maintainable architecture with clear separation of concerns.

## Architecture Pattern

**Before:**
```
OPNsenseProvider
  ├── reset_kea_dhcpv4() (40+ lines inline)
  ├── reset_kea_dhcpv6() (47+ lines inline)
  └── migrate_kea_dhcp() (140+ lines inline)
```

**After:**
```
OPNsenseProvider (thin delegation layer)
  ├── reset_kea_dhcpv4() → KeaDHCPManager.reset_dhcpv4()
  ├── reset_kea_dhcpv6() → KeaDHCPManager.reset_dhcpv6()
  └── migrate_kea_dhcp() → KeaDHCPManager.migrate()
        ↓
Component Manager (orchestration layer)
  ├── KeaDHCPManager
        ├── reset_dhcpv4() - orchestrates v4 reset
        ├── reset_dhcpv6() - orchestrates v6 reset
        ├── reset_all() - resets both v4 and v6
        └── migrate() - orchestrates migration
        ↓
Service Layer (API operations layer)
  ├── BaseService (factory pattern with from_environment())
  └── KeaDHCPService (all DHCP operations)
        ├── search_dhcpv4_reservations()
        ├── delete_dhcpv4_reservation(uuid)
        ├── delete_all_dhcpv4_reservations()
        ├── search_dhcpv4_subnets()
        ├── delete_dhcpv4_subnet(uuid)
        ├── delete_all_dhcpv4_subnets()
        ├── search_dhcpv6_reservations()
        ├── delete_dhcpv6_reservation(uuid)
        ├── delete_all_dhcpv6_reservations()
        ├── search_dhcpv6_subnets()
        ├── delete_dhcpv6_subnet(uuid)
        ├── delete_all_dhcpv6_subnets()
        ├── reconfigure()
        └── export_to_yaml()
```

## Code Metrics

- **Provider file**: 604 → 415 lines (-31% reduction)
- **New service layer**: 264 lines (reusable API operations)
- **New component manager**: 86 lines (orchestration logic)
- **Total code**: 765 lines (distributed across 3 layers)
- **Tests**: 8 passing tests (simplified delegation tests)

## Benefits

### 1. Modularity
- Each layer has a single, clear responsibility
- Easy to add new component managers (ISC DHCP, Firewall, Interfaces)
- Service operations are independently reusable

### 2. Testability
- Can mock at any layer (service, manager, or provider)
- Service layer can be unit tested in isolation
- Manager layer orchestration can be tested independently

### 3. Maintainability
- Provider stays thin and focused on Terraform/Ansible generation
- Business logic centralized in component managers
- API operations grouped logically in services

### 4. Extensibility
Example: Adding a new firewall component manager:

```python
# src/infrafoundry/providers/opnsense/services/firewall.py
class FirewallService(BaseService):
    def search_rules(self): ...
    def create_rule(self, rule_config): ...
    def delete_rule(self, uuid): ...

# src/infrafoundry/providers/opnsense/components/firewall.py
class FirewallManager(BaseComponentManager):
    def reset_rules(self, env_name, provider_name): ...
    def migrate(self, env_name, provider_name): ...

# Provider delegation (3 lines)
def reset_firewall_rules(self, env_name: str) -> None:
    from .components.firewall import FirewallManager
    manager = FirewallManager(self.config_dir)
    manager.reset_rules(env_name, "opnsense")
```

### 5. CLI Integration
Commands can use services/managers directly:

```python
# Option 1: Use manager directly (bypassing provider)
from infrafoundry.providers.opnsense.components.kea_dhcp import KeaDHCPManager
manager = KeaDHCPManager(config_dir)
manager.reset_dhcpv4(env_name, provider_name)

# Option 2: Use service directly (for custom operations)
from infrafoundry.providers.opnsense.services.kea_dhcp import KeaDHCPService
service = KeaDHCPService.from_environment(env_name, provider_name, config_dir)
reservations = service.search_dhcpv4_reservations()
```

## Directory Structure

```
src/infrafoundry/providers/opnsense/
├── __init__.py                   # OPNsenseProvider (415 lines, -31%)
├── api_client.py                 # Low-level HTTP client
├── services/                     # NEW: Service layer
│   ├── __init__.py
│   ├── base.py                   # BaseService with factory pattern
│   └── kea_dhcp.py               # KeaDHCPService (264 lines)
└── components/                   # NEW: Component manager layer
    ├── __init__.py
    ├── base.py                   # BaseComponentManager
    └── kea_dhcp.py               # KeaDHCPManager (86 lines)
```

## Factory Pattern

The `BaseService.from_environment()` classmethod provides a clean way to create services:

```python
class BaseService(ABC):
    @classmethod
    def from_environment(
        cls, env_name: str, provider_name: str, config_dir: Path
    ) -> "BaseService":
        """Create service instance from environment configuration."""
        config_manager = ConfigManager(config_dir)
        env_config = config_manager.load_environment(env_name)
        provider_settings = env_config.get_provider_settings(provider_name)
        
        if not provider_settings:
            raise ValueError(f"No {provider_name} provider settings...")
        
        client = OPNsenseClient(
            api_key=provider_settings.get("api_key", ""),
            api_secret=provider_settings.get("api_secret", ""),
            base_url=provider_settings.get("api_url", ""),
            verify_ssl=provider_settings.get("verify_ssl", True),
        )
        
        return cls(client)
```

## Type Hints Fix

Due to Python's limitations with factory methods returning specific subclasses, we use type annotations:

```python
# Without annotation: Pylance thinks it's BaseService
service = KeaDHCPService.from_environment(env_name, provider_name, config_dir)

# With annotation: Pylance understands it's KeaDHCPService
service: KeaDHCPService = KeaDHCPService.from_environment(  # type: ignore[assignment]
    env_name, provider_name, config_dir
)
```

## Next Steps

### Easy wins:
1. Add `ISCDHCPManager` for legacy DHCP (same pattern)
2. Add `FirewallManager` for firewall rules
3. Add `InterfaceManager` for VLAN management
4. Add `AliasManager` for IP/network aliases

### Future enhancements:
1. Add service-level caching for repeated API calls
2. Add batch operations in services (delete multiple resources at once)
3. Add validation layer between manager and service
4. Add retry logic in services for transient API failures
5. Add async support for parallel operations

## Testing Strategy

**Unit tests** (mock at service layer):
```python
@patch("...KeaDHCPService")
def test_manager_operation(mock_service):
    manager = KeaDHCPManager(config_dir)
    manager.reset_dhcpv4(env_name, provider_name)
    mock_service.delete_all_dhcpv4_reservations.assert_called()
```

**Integration tests** (test full stack):
```python
def test_reset_integration():
    provider = OPNsenseProvider(config_dir, output_dir)
    provider.reset_kea_dhcpv4(env_name)
    # Verify actual API calls happened
```

**Provider tests** (test delegation):
```python
@patch("...KeaDHCPManager")
def test_provider_delegates(mock_manager):
    provider.reset_kea_dhcpv4(env_name)
    mock_manager.reset_dhcpv4.assert_called_once_with(env_name, "opnsense")
```

## Conclusion

This refactoring demonstrates a production-ready architecture pattern that:
- Separates concerns cleanly (Provider → Manager → Service → Client)
- Makes testing straightforward at each layer
- Enables easy extension without modifying existing code
- Keeps the provider thin and focused on its core responsibility
- Provides reusable building blocks for future features

The pattern is repeatable and can be applied to any provider that needs component-level operations beyond Terraform/Ansible generation.
