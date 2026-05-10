"""Shared helper for secret-bearing field validators (#806).

Singleton components with secret-bearing fields (``system.remotebackup``,
and any future surfaces with API keys / passwords / certificates) all
need the same plan-time check: the operator MUST supply a
``secret://env_secrets/<dotted/path>`` URI for each secret field;
literal plaintext is rejected.

This module owns the regex + helper so every validator imports the same
shape rather than re-inventing slightly different patterns. The check is
pure-string: no resolution happens at plan time (resolution is the
component manager's apply-time concern).

The ``secret://`` URI shape (``secret://<backend>/<path>``) follows the
project-wide convention used by ``EnvSecretsBackend`` and the resolver
in ``infrafoundry.secrets.resolver``.
"""

from __future__ import annotations

import re

# Match ``secret://<backend>/<path>``. The validator does NOT resolve at
# plan time; it only confirms the shape so a plaintext password isn't
# silently accepted as a "secret reference".
_SECRET_URI = re.compile(r"^secret://[^/]+/.+$")


def is_secret_reference(value: object) -> bool:
    """Return True iff *value* looks like a ``secret://backend/path`` URI.

    Args:
        value: Field value from a ``ResourceConfig.config`` dict.

    Returns:
        ``True`` when ``value`` is a string matching the secret-URI
        pattern; ``False`` for any other value (including non-strings,
        empty strings, and plaintext that resembles a URI but doesn't
        match the strict ``secret://<backend>/<path>`` shape).
    """
    if not isinstance(value, str):
        return False
    return bool(_SECRET_URI.match(value))
