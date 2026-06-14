"""Tailscale auth validator for OPNsense (#787).

Plan-time validation for the ``tailscale.auth`` dotted resource type —
a dict-shape singleton. The validator is pure-check; it never mutates
``resource.config``.

Field-shape checks:

- ``login_server``: optional URL string. If provided, must look like a
  URL (starts with ``https://`` or ``http://``).
- ``pre_auth_key``: optional string. If provided AND does not look like a
  ``secret://`` URI, a soft warning is emitted (plaintext keys should be
  stored in secrets, not in YAML). Empty string is accepted (means "no
  key configured").
"""

from __future__ import annotations

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport

from ._secrets import is_secret_reference


class TailscaleAuthValidator:
    """Validates the ``tailscale.auth`` singleton resource.

    Args:
        report: ``ValidationReport`` to add results to.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: Validation report to populate.
        """
        self.report = report

    def validate(self, resources: list[ResourceConfig]) -> None:
        """Validate the tailscale.auth singleton.

        Args:
            resources: ``tailscale.auth`` ``ResourceConfig`` entries
                (zero or one). Zero resources is valid (feature not used).
        """
        if not resources:
            return
        for resource in resources:
            self._validate_one(resource)

    def _validate_one(self, resource: ResourceConfig) -> None:
        """Validate a single tailscale.auth resource."""
        config = resource.config

        # login_server: optional URL
        login_server = config.get("login_server")
        if login_server is not None and login_server != "":
            if not isinstance(login_server, str):
                self.report.add_check(
                    check_name=f"tailscale.auth[{resource.name}].login_server",
                    passed=False,
                    message=(f"login_server must be a string, got {type(login_server).__name__}"),
                    level=ValidationLevel.ERROR,
                )
            elif not (login_server.startswith("https://") or login_server.startswith("http://")):
                self.report.add_check(
                    check_name=f"tailscale.auth[{resource.name}].login_server",
                    passed=False,
                    message=(
                        f"login_server must be a URL starting with https:// or http://, "
                        f"got {login_server!r}"
                    ),
                    level=ValidationLevel.ERROR,
                )

        # pre_auth_key: soft warning for plaintext keys
        pre_auth_key = config.get("pre_auth_key")
        if pre_auth_key is not None and pre_auth_key != "":
            if not isinstance(pre_auth_key, str):
                self.report.add_check(
                    check_name=f"tailscale.auth[{resource.name}].pre_auth_key",
                    passed=False,
                    message=(
                        f"pre_auth_key must be a string or secret:// URI, "
                        f"got {type(pre_auth_key).__name__}"
                    ),
                    level=ValidationLevel.ERROR,
                )
            elif not is_secret_reference(pre_auth_key):
                self.report.add_check(
                    check_name=f"tailscale.auth[{resource.name}].pre_auth_key",
                    passed=False,
                    message=(
                        "pre_auth_key is a plaintext value. "
                        "Consider using a secret:// URI (e.g. "
                        "secret://env_secrets/tailscale/pre_auth_key) "
                        "to avoid committing secrets to YAML."
                    ),
                    level=ValidationLevel.WARNING,
                )
