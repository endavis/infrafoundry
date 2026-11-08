"""Validation contexts for the ESXi sub-validators.

The reference and OVF validators check ``ValidationContext.resources`` directly,
so only the host connectivity validator needs a context of its own.
"""

from dataclasses import dataclass

from infrafoundry.core.validation import ValidationContext


@dataclass(frozen=True, kw_only=True)
class EsxiHostContext(ValidationContext):
    """Context for checking SSH connectivity to one ESXi host.

    Attributes:
        hostname: Host name or IP address to check.
        port: Port to check (22 for SSH).
    """

    hostname: str
    port: int = 22
