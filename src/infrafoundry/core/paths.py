"""The one place that decides where generated files live (#1716).

``INFRAFOUNDRY_OUTPUT_DIR`` chooses the ``generated/`` root. Every code path that reads or
writes generated files calls :func:`output_root`, so a relative value is made absolute once,
against the current directory, and all paths agree.
"""

from __future__ import annotations

import os
from pathlib import Path

OUTPUT_DIR_ENV: str = "INFRAFOUNDRY_OUTPUT_DIR"
"""Name of the environment variable that overrides the generated root."""

DEFAULT_OUTPUT_DIR: str = "generated"
"""The generated root, relative to the current directory, when the variable is unset."""


def output_root() -> Path:
    """Return the absolute generated root.

    An unset, empty or whitespace-only ``INFRAFOUNDRY_OUTPUT_DIR`` counts as unset.

    Returns:
        ``INFRAFOUNDRY_OUTPUT_DIR`` or ``generated``, with ``~`` expanded and made absolute.
    """
    value = os.environ.get(OUTPUT_DIR_ENV, "").strip()
    return Path(value or DEFAULT_OUTPUT_DIR).expanduser().resolve()
