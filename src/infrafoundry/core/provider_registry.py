"""Provider registry for auto-discovery and management of infrastructure providers."""

import importlib
import logging
import traceback
import types
from pathlib import Path
from typing import Any, cast

from infrafoundry.core.exceptions import ProviderInitializationError
from infrafoundry.core.provider import ProviderBase

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry for discovering and managing infrastructure providers.

    Auto-discovers provider plugins from the providers/ directory and
    creates instances with proper configuration.
    """

    def __init__(self, config_dir: Path, output_dir: Path) -> None:
        """Initialize provider registry.

        Args:
            config_dir: Directory containing provider configurations
            output_dir: Directory for generated Terraform/Ansible files
        """
        self.config_dir = config_dir
        self.output_dir = output_dir
        self._providers: dict[str, ProviderBase] = {}

    def discover_and_register_all(self) -> None:
        """Auto-discover all available providers and register them.

        Scans the providers/ directory for provider implementations and
        automatically instantiates and registers them.
        """
        providers_path = Path(__file__).parent.parent / "providers"

        if not providers_path.exists():
            logger.warning(f"Providers directory not found: {providers_path}")
            return

        for provider_dir in providers_path.iterdir():
            if not provider_dir.is_dir():
                continue

            # Skip __pycache__ and other non-provider directories
            if provider_dir.name.startswith("_"):
                continue

            init_file = provider_dir / "__init__.py"
            if not init_file.exists():
                continue

            try:
                self._discover_and_register_provider(provider_dir.name)
            except ProviderInitializationError as e:
                logger.debug(f"Could not load provider '{provider_dir.name}': {e}")
            except (ImportError, SyntaxError) as e:
                logger.warning(f"Failed to import provider '{provider_dir.name}': {e}")
            except Exception as e:
                logger.error(f"Unexpected error discovering provider '{provider_dir.name}': {e}")
                logger.debug(traceback.format_exc())  # Log full traceback

    def _discover_and_register_provider(self, provider_name: str) -> None:
        """Discover and register a specific provider by name.

        Args:
            provider_name: Name of the provider directory (e.g., 'proxmox')
        """
        module_path = f"infrafoundry.providers.{provider_name}"

        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            logger.debug(f"Cannot import {module_path}: {e}")
            return

        # Find the provider class (subclass of ProviderBase)
        if provider_class := self._find_provider_class(module, provider_name):
            try:
                ctor = cast(Any, provider_class)
                try:
                    # Most providers expect (config_dir, output_dir)
                    provider_instance = ctor(self.config_dir, self.output_dir)
                except TypeError:
                    # Fallback for providers that expect (name, config_dir, output_dir)
                    provider_instance = ctor(provider_name, self.config_dir, self.output_dir)
                self.register_provider(cast(ProviderBase, provider_instance))
                logger.debug(f"Registered provider: {provider_name}")
            except Exception as e:
                # Wrap instantiation failures as ProviderInitializationError
                logger.debug(f"Failed to instantiate {provider_name}: {e}")
                logger.debug(traceback.format_exc())  # Log full traceback
                raise ProviderInitializationError(
                    f"Failed to initialize provider '{provider_name}'",
                    context={"provider": provider_name, "error": str(e)},
                ) from e

    def _find_provider_class(
        self, module: types.ModuleType, provider_name: str
    ) -> type[ProviderBase] | None:
        """Find the provider class in a module.

        Args:
            module: The imported provider module
            provider_name: Name of the provider (used for logging)

        Returns:
            Provider class if found, None otherwise
        """
        for attr_name in dir(module):
            try:
                attr = getattr(module, attr_name)

                # Check if it's a class that subclasses ProviderBase
                if (
                    isinstance(attr, type)
                    and issubclass(attr, ProviderBase)
                    and attr is not ProviderBase
                ):
                    return attr
            except (AttributeError, TypeError):
                continue

        return None

    def register_provider(self, provider: ProviderBase) -> None:
        """Register a provider instance.

        Args:
            provider: Provider instance to register
        """
        self._providers[provider.name] = provider
        logger.info(f"Registered provider: {provider.name}")

    def get_provider(self, name: str) -> ProviderBase | None:
        """Get a registered provider by name.

        Args:
            name: Provider name (e.g., 'proxmox', 'opnsense')

        Returns:
            Provider instance if registered, None otherwise
        """
        return self._providers.get(name)

    def get_all_providers(self) -> dict[str, ProviderBase]:
        """Get all registered providers.

        Returns:
            Dictionary mapping provider names to instances
        """
        return self._providers.copy()

    def has_provider(self, name: str) -> bool:
        """Check if a provider is registered.

        Args:
            name: Provider name

        Returns:
            True if provider is registered
        """
        return name in self._providers
