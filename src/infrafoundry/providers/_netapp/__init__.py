"""Shared service layer for the NetApp provider family (ADR-0042).

``ontap`` is the first sibling; ``aiqum``, ``dii`` and ``console`` follow and reuse this
package. Everything here wraps pynetappfoundry, which ships in the optional
``infrafoundry[netapp]`` extra, so nothing in this package imports it at import time:
the providers always register, and a core-only install fails with a clear message when
a run first needs the library.
"""

from __future__ import annotations

import importlib
from types import ModuleType

from infrafoundry.core.exceptions import InfraFoundryError

LIBRARY = "pynetappfoundry"
EXTRA = "netapp"


class NetAppDependencyError(InfraFoundryError):
    """pynetappfoundry is not installed (the ``netapp`` extra is missing)."""


def require_pynetappfoundry() -> ModuleType:
    """Import pynetappfoundry on first use.

    Returns:
        The imported ``pynetappfoundry`` module.

    Raises:
        NetAppDependencyError: If the library is not installed. The message names the extra.
    """
    try:
        return importlib.import_module(LIBRARY)
    except ImportError as exc:
        raise NetAppDependencyError(
            f"{LIBRARY} is not installed; install it with: pip install 'infrafoundry[{EXTRA}]'"
        ) from exc


__all__ = ["EXTRA", "LIBRARY", "NetAppDependencyError", "require_pynetappfoundry"]
