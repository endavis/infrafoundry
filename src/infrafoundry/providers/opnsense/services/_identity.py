"""Shared description-suffix identity helpers for OPNsense direct-API services.

Firewall rules, NAT rules and cron jobs are plain rows with no stable key
that survives a round trip, so each managed row carries its resource name in
its ``description`` as a suffix: ``<user description> [infrafoundry:<name>]``
(or just ``[infrafoundry:<name>]`` when the description is empty). This
module is the one definition of that scheme: the strict parse regex, the
position-agnostic probe, the drift error, and the encode, parse and
presence-check helpers.
"""

from __future__ import annotations

import re

from infrafoundry.core.exceptions import InfraFoundryError

# Strict regex for parsing the description-suffix identity tag. The
# (optional) free-form user description leads, followed by whitespace,
# followed by ``\[infrafoundry:<name>\]`` at the end of the string. The
# name must be a non-empty match of ``[a-z0-9-]+``; live rows without the
# tag are unmanaged, and rows with a malformed tag raise
# ``OpnsenseDriftError``. ``_IDENTITY_PROBE`` is a position-agnostic
# detector used both by the parser (to flag malformed tags) and by the
# validators (to reject operator-set descriptions that include the tag
# pattern, since InfraFoundry adds it automatically).
_IDENTITY_PATTERN = re.compile(r"^(?:(.+?)\s+)?\[infrafoundry:([a-z0-9-]+)\]\s*$")
_IDENTITY_PROBE = re.compile(r"\[infrafoundry:[^\]]*\]")


class OpnsenseDriftError(InfraFoundryError):
    """A managed record's identity tag is malformed on the live box.

    Raised by the diff engine when a live record's ``description`` looks
    like it carries an InfraFoundry tag but does not match the strict
    identity regex. The operator must repair the description in the GUI
    (or via API) before the next plan/apply.
    """


def encode_identity(resource_name: str, user_description: str) -> str:
    """Encode the description with the InfraFoundry identity suffix.

    Args:
        resource_name: Operator-facing YAML name; becomes the diff key.
        user_description: Free-form description from YAML (may be empty).

    Returns:
        ``"<user_description> [infrafoundry:<name>]"`` when the user
        description is non-empty; ``"[infrafoundry:<name>]"`` otherwise.
    """
    if user_description:
        return f"{user_description} [infrafoundry:{resource_name}]"
    return f"[infrafoundry:{resource_name}]"


def has_identity_marker(description: str) -> bool:
    """Report whether ``description`` contains an identity marker in any position.

    Args:
        description: A description string, well-formed or not.

    Returns:
        ``True`` when an ``[infrafoundry:...]`` marker appears anywhere.
    """
    return _IDENTITY_PROBE.search(description) is not None


def parse_identity(description: str, *, record_label: str = "Record") -> tuple[str | None, str]:
    """Parse the description-suffix identity tag.

    Args:
        description: ``description`` field from a live row.
        record_label: Noun that opens the drift-error message, for example
            ``"Firewall rule"``.

    Returns:
        ``(resource_name, user_description)``. ``resource_name`` is ``None``
        when the description has no tag (unmanaged row).

    Raises:
        OpnsenseDriftError: If the description contains the
            ``[infrafoundry:...]`` marker but does not match the strict
            suffix-only regex.
    """
    match = _IDENTITY_PATTERN.match(description)
    if match is not None:
        user_desc = match.group(1) or ""
        return match.group(2), user_desc
    if _IDENTITY_PROBE.search(description):
        raise OpnsenseDriftError(
            f"{record_label} description contains an InfraFoundry identity tag but is malformed: "
            f"{description!r}. Expected '<user description> [infrafoundry:<name>]' (or just "
            f"'[infrafoundry:<name>]') where <name> matches [a-z0-9-]+ (non-empty) and the "
            f"tag is the LAST token in the description."
        )
    return None, description
