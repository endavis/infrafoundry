"""OPNsense component manager implementations."""

from .base import BaseComponentManager
from .kea_dhcp import KeaDHCPManager

__all__ = ["BaseComponentManager", "KeaDHCPManager"]
