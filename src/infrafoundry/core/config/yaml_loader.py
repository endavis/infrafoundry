"""libyaml-backed YAML parsing for configuration files.

Parsing with the pure-Python ``yaml.SafeLoader`` dominates config loading time. When PyYAML was
built with libyaml, ``yaml.CSafeLoader`` parses the same documents several times faster (#243).
:func:`load_config_yaml` uses it when available and falls back to ``yaml.SafeLoader`` otherwise.
Both are safe loaders: neither constructs arbitrary Python objects.
"""

from typing import IO, Any

import yaml


def _safe_loader_class() -> type[yaml.SafeLoader] | type[yaml.CSafeLoader]:
    """Pick the fastest safe loader available.

    The choice is made per call, so tests can simulate a PyYAML build without libyaml.

    Returns:
        ``yaml.CSafeLoader`` when libyaml is present, else ``yaml.SafeLoader``.
    """
    c_loader: type[yaml.CSafeLoader] | None = getattr(yaml, "CSafeLoader", None)
    if yaml.__with_libyaml__ and c_loader is not None:
        return c_loader
    return yaml.SafeLoader


def load_config_yaml(stream: str | IO[str]) -> Any:
    """Parse a YAML document like ``yaml.safe_load``, using libyaml when available.

    Args:
        stream: YAML text or an open text file.

    Returns:
        The parsed document (``None`` for an empty document).

    Raises:
        yaml.YAMLError: If the document is not valid YAML.
    """
    # Name the loader class directly rather than passing the selector's result: bandit
    # (B506) only recognises a safe loader written out in the call.
    if _safe_loader_class() is yaml.SafeLoader:
        return yaml.safe_load(stream)
    return yaml.load(stream, Loader=yaml.CSafeLoader)
