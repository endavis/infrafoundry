"""Custom Jinja2 filters for InfraFoundry configuration rendering."""

import hashlib


def generate_mac(value: str) -> str:
    """Generate a deterministic locally-administered MAC address from a string.

    Uses SHA-256 to hash the input, then formats the first 5 bytes as a
    MAC address with a fixed ``02`` first octet (locally administered,
    unicast).

    Args:
        value: Input string to derive the MAC address from.

    Returns:
        MAC address in the format ``02:xx:xx:xx:xx:xx``.
    """
    digest = hashlib.sha256(value.encode()).digest()
    return "02:{:02x}:{:02x}:{:02x}:{:02x}:{:02x}".format(*digest[:5])
