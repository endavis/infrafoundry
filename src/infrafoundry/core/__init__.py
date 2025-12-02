"""
InfraFoundry Core Package.

This package contains the core framework components.
"""

from infrafoundry.core.config import ConfigManager, EnvironmentConfig
from infrafoundry.core.orchestrator import Orchestrator, OrchestratorStrictConfig
from infrafoundry.core.protocols import (
    Applyable,
    Destroyable,
    DriftDetectable,
    HasLogger,
    HasPathResolution,
    HasResourceGrouper,
    HasStructuredLogging,
    HasTemplateRenderer,
    Plannable,
    StateAware,
)
from infrafoundry.core.provider import ProviderBase, ResourceConfig
from infrafoundry.core.secrets.secret_manager import SecretManager

__all__ = [
    "Applyable",
    "ConfigManager",
    "Destroyable",
    "DriftDetectable",
    "EnvironmentConfig",
    "HasLogger",
    "HasPathResolution",
    "HasResourceGrouper",
    "HasStructuredLogging",
    "HasTemplateRenderer",
    "Orchestrator",
    "OrchestratorStrictConfig",
    "Plannable",
    "ProviderBase",
    "ResourceConfig",
    "SecretManager",
    "StateAware",
]
