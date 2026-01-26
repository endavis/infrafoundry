"""Lifecycle hooks for infrastructure operations.

This module provides user-defined script execution at specific points
during plan, apply, and destroy operations.
"""

from infrafoundry.core.hooks.manager import HookExecutionError, HookManager
from infrafoundry.core.hooks.models import HookConfig, HookResult, HooksConfig

__all__ = [
    "HookConfig",
    "HookExecutionError",
    "HookManager",
    "HookResult",
    "HooksConfig",
]
