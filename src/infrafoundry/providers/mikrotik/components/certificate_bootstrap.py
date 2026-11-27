"""Lock-out guards for the certificate switch-over (``www`` to ``www-ssl``).

The switch-over runs in separate applies, each one safe on its own: create and sign
a certificate while ``www`` still carries the connection, point ``www-ssl`` and
``api-ssl`` at it, move ``api_url`` to ``https``, and only then optionally disable
``www`` (``ordering.check_service_changes`` already refuses that while ``api_url``
is ``http``). Three guards keep one apply from breaking that order:

* a service may only name a certificate that exists signed after the plan, because
  RouterOS accepts the name and then fails the TLS handshake;
* a certificate a live service still references is not deleted; switch the service
  in an earlier apply;
* with ``api_url`` on ``https`` and ``verify_ssl`` on, ``www-ssl`` is not pointed at
  a certificate this plan creates, because a self-signed certificate cannot validate
  and the next connection would fail.

Everything here is a function of its arguments; no client is involved.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..schema import SIGN_FIELD
from .diff import CREATE, DELETE, SIGN, UPDATE, TypeDiff
from .ordering import LiveState, PathCheck

_CERTIFICATE = "certificate"
_SERVICE = "ip.service"
_WWW_SSL = "www-ssl"


def _signed_after_plan(diffs: Mapping[str, TypeDiff], live: LiveState) -> tuple[set[str], set[str]]:
    """Return the certificate names that exist signed after the plan, and the created ones."""
    changes = diffs.get(_CERTIFICATE, TypeDiff(_CERTIFICATE)).changes
    created = {str(c.key[0]) for c in changes if c.kind == CREATE}
    deleted = {str(c.key[0]) for c in changes if c.kind == DELETE}
    to_sign = {str(c.key[0]) for c in changes if c.kind == SIGN}
    signed = {
        row["name"]
        for row in live.get(_CERTIFICATE, [])
        if row.get("name") and str(row.get(SIGN_FIELD, "")).strip()
    }
    return ((signed | created | to_sign) - deleted, created)


def check_certificate_changes(
    diffs: Mapping[str, TypeDiff],
    live: LiveState,
    *,
    scheme: str,
    verify_ssl: bool,
) -> PathCheck:
    """Refuse certificate and service changes that would lock InfraFoundry out.

    Args:
        diffs: Diff per type.
        live: Live rows per type (``certificate`` and ``ip.service`` are read).
        scheme: ``http`` or ``https`` from ``api_url``.
        verify_ssl: Whether the client verifies the device certificate.

    Returns:
        Refusal reasons (empty when safe) and warnings.
    """
    check = PathCheck()
    available, created = _signed_after_plan(diffs, live)
    for change in diffs.get(_SERVICE, TypeDiff(_SERVICE)).changes:
        if change.kind != UPDATE or "certificate" not in change.changed:
            continue
        name = str(change.key[0])
        cert = str(change.after.get("certificate") or "")
        if not cert:
            continue
        if cert not in available:
            check.refusals.append(
                f"ip.service '{name}' names certificate '{cert}', which will not exist "
                "signed after the plan"
            )
        elif scheme == "https" and verify_ssl and name == _WWW_SSL and cert in created:
            check.refusals.append(
                f"ip.service '{name}' would use the new certificate '{cert}', which is "
                "self-signed, while api_url is https with verify_ssl on; set verify_ssl "
                "to false first"
            )
    for change in diffs.get(_CERTIFICATE, TypeDiff(_CERTIFICATE)).changes:
        if change.kind != DELETE:
            continue
        cert = str(change.key[0])
        for row in live.get(_SERVICE, []):
            if row.get("certificate") == cert:
                check.refusals.append(
                    f"certificate '{cert}' cannot be deleted while ip.service "
                    f"'{row.get('name', '')}' uses it; switch the service in an earlier apply"
                )
    return check
