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
        self.base_dir = self._resolve_path(
            base_dir,
            env_var="INFRAFOUNDRY_CONFIG_DIR",
            default="envs",
            create=True  # Create if doesn't exist
        )
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

### Backward Compatibility

All existing code continues to work without changes. The patterns are additive and don't break existing functionality.
