"""HCL string helpers for the Tailscale templates.

Tailscale policy text and tag lists reach Terraform as HCL string literals. A
JSON string is a valid HCL string except for template sequences: HCL expands
``${...}`` and ``%{...}`` inside a quoted string. Policy text can contain them
(a ``// comment`` quoting a shell variable, say), so both are escaped by
doubling the first character, which makes HCL emit them literally.
"""

from __future__ import annotations

import json
from collections.abc import Iterable


def hcl_string(value: str) -> str:
    """Render ``value`` as a quoted HCL string literal with no interpolation.

    Args:
        value: The text to embed.

    Returns:
        A double-quoted literal. Quotes, backslashes and control characters are
        JSON-escaped; ``${`` becomes ``$${`` and ``%{`` becomes ``%%{``.
    """
    literal = json.dumps(str(value))
    return literal.replace("${", "$${").replace("%{", "%%{")


def hcl_list(values: Iterable[str]) -> str:
    """Render strings as an HCL list literal.

    Args:
        values: The strings to embed, each escaped as by :func:`hcl_string`.

    Returns:
        ``[...]`` with the elements comma-separated on one line.
    """
    return "[" + ", ".join(hcl_string(v) for v in values) + "]"
