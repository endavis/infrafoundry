"""Trust-store service for OPNsense direct-API operations (ADR-0014, #807).

Manages the OPNsense trust store through the ``trust/ca`` and ``trust/cert``
controllers: certificate authorities (``trust.cas``) and certificates
(``trust.certs``). Both are list-shape types on the managed-set delete scope
(ADR-0018); ``trust.certs`` is the child of ``trust.cas`` (sibling pattern).

Identity is the live ``descr`` against the YAML ``description`` (falling back
to the resource ``name``). ``refid`` and ``serial`` are assigned by the box and
are not YAML fields.

What is verified and what is not:

- Verified read-only against a test firewall: ``GET trust/cert/search`` rows
  carry ``uuid, refid, descr, caref, crt, csr, prv`` (base64), the raw PEM
  twins ``crt_payload, csr_payload, prv_payload``, ``cert_type`` and ``in_use``.
- Verified by a live apply on a test firewall: there is no ``import``
  endpoint; an import is an ``add`` whose body carries an ``action``
  (``existing`` for a CA, ``import`` for a certificate) plus the ``*_payload``
  fields. ``caref`` links to the resolved CA, ``set`` re-imports a changed
  ``crt`` in place (same ``uuid`` and ``refid``), and the box ignores
  ``cert_type`` on import (the stored type follows the certificate).
- Not verified: whether the box refuses to delete an in-use object.

Secrets: ``prv`` should be a ``secret://`` URI. The manager resolves it; this
module only ever sees plaintext and never logs, formats or raises anything
derived from ``crt``, ``prv`` or ``csr``. Dataclass ``repr`` hides those fields.
"""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from infrafoundry.core.exceptions import ReferenceValidationError
from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from ._identity import OpnsenseDriftError
from .base import BaseService, raise_on_failed_write

TrustKind = Literal["ca", "cert"]

#: Descriptions the AcmeClient plugin gives the CAs it imports (``R10``, ``E5``, ...).
#: Inference about plugin naming; matched on ``descr`` because ``refid`` is a
#: box-generated uniqid with no ACME pattern.
ACME_ISSUED_CA_DESCR = r"^(?:R|E)\d+$"
_ACME_ISSUED_CA_RE = re.compile(ACME_ISSUED_CA_DESCR)

#: YAML ``type`` value to the wire ``cert_type`` value. The box ignores it on
#: import (the stored type follows the certificate); see the module docstring.
CERT_TYPE_WIRE: dict[str, str] = {
    "server": "server_cert",
    "client": "usr_cert",
    "combined": "combined_server_client",
}
ALLOWED_CERT_TYPES: tuple[str, ...] = tuple(CERT_TYPE_WIRE)

_PEM_BEGIN = "-----BEGIN "
_PEM_END = "-----END "

_PRIVATE_KEY_MARKERS = ("PRIVATE KEY-----",)


def is_acme_issued_descr(description: str) -> bool:
    """Return True if a CA description looks like one the AcmeClient plugin imported.

    Args:
        description: The live ``descr`` of a CA.
    """
    return _ACME_ISSUED_CA_RE.match(description) is not None


def normalize_pem(value: str) -> str:
    """Collapse a PEM string to a comparable form.

    Strips surrounding whitespace on every line and drops blank lines, so
    line-ending and trailing-newline differences do not read as drift.

    Args:
        value: PEM text, possibly empty.

    Returns:
        The lines joined by a single newline.
    """
    return "\n".join(line.strip() for line in value.splitlines() if line.strip())


def has_pem_markers(value: str) -> bool:
    """Return True if ``value`` has a PEM BEGIN line and an END line."""
    normalized = normalize_pem(value)
    return normalized.startswith(_PEM_BEGIN) and _PEM_END in normalized


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrustCaConfig:
    """Desired-state certificate authority.

    Attributes:
        name: Operator-facing YAML name.
        description: Wire ``descr`` and the identity (defaults to ``name``).
        crt: PEM certificate (plaintext after secret resolution).
        prv: Optional PEM private key (plaintext after secret resolution).
        lock: Per-resource safety annotation (ADR-0014 section 6).
    """

    name: str
    description: str
    crt: str = field(repr=False)
    prv: str = field(default="", repr=False)
    lock: bool = False

    @property
    def diff_key(self) -> str:
        """Identity of this CA: its description."""
        return self.description

    def to_payload(self, caref: str = "") -> dict[str, Any]:
        """Serialize to the ``add``/``set`` envelope.

        Args:
            caref: Ignored; a CA has no parent reference here.

        Returns:
            ``{"ca": {...}}``. The private key is omitted when empty.
        """
        del caref
        body: dict[str, Any] = {
            "action": "existing",
            "descr": self.description,
            "crt_payload": self.crt,
        }
        if self.prv:
            body["prv_payload"] = self.prv
        return {"ca": body}


@dataclass(frozen=True)
class TrustCertConfig:
    """Desired-state certificate.

    Attributes:
        name: Operator-facing YAML name.
        description: Wire ``descr`` and the identity (defaults to ``name``).
        crt: PEM certificate (plaintext after secret resolution).
        prv: PEM private key (plaintext after secret resolution).
        csr: Optional PEM certificate signing request.
        ca_ref: Name of the ``trust.cas`` resource that signed it, or empty.
        type: ``server``, ``client`` or ``combined``, or empty to leave to the box.
        lock: Per-resource safety annotation (ADR-0014 section 6).
    """

    name: str
    description: str
    crt: str = field(repr=False)
    prv: str = field(default="", repr=False)
    csr: str = field(default="", repr=False)
    ca_ref: str = ""
    type: str = ""
    lock: bool = False

    @property
    def diff_key(self) -> str:
        """Identity of this certificate: its description."""
        return self.description

    def to_payload(self, caref: str = "") -> dict[str, Any]:
        """Serialize to the ``add``/``set`` envelope.

        Args:
            caref: Resolved ``refid`` of the signing CA; omitted when empty.

        Returns:
            ``{"cert": {...}}``. Empty optional fields are omitted.
        """
        body: dict[str, Any] = {
            "action": "import",
            "descr": self.description,
            "crt_payload": self.crt,
        }
        if self.prv:
            body["prv_payload"] = self.prv
        if self.csr:
            body["csr_payload"] = self.csr
        if caref:
            body["caref"] = caref
        if self.type:
            body["cert_type"] = CERT_TYPE_WIRE[self.type]
        return {"cert": body}


TrustConfig = TrustCaConfig | TrustCertConfig


@dataclass(frozen=True)
class LiveTrustObject:
    """A CA or certificate as currently on the box (a ``search`` row).

    Attributes:
        uuid: Row UUID.
        refid: Box-assigned reference id.
        description: Live ``descr``.
        caref: Signing CA ``refid`` (certificates only; may be empty).
        in_use: Whether the box reports the object as in use.
        crt: Raw PEM certificate from ``crt_payload`` (or decoded ``crt``).
        prv: Raw PEM private key, empty when the row does not expose it.
        csr: Raw PEM request, empty when absent.
        raw: The full search row.
    """

    uuid: str
    refid: str
    description: str
    caref: str = ""
    in_use: bool = False
    crt: str = field(default="", repr=False)
    prv: str = field(default="", repr=False)
    csr: str = field(default="", repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def diff_key(self) -> str:
        """Identity of this object: its description."""
        return self.description


@dataclass
class Diff[C: (TrustCaConfig, TrustCertConfig)]:
    """Result of comparing desired YAML state to live state.

    ``blocked`` holds managed live objects that would be deleted but must stay
    (in use, or issued by the AcmeClient plugin), each with the reason. They are
    kept and reported, never deleted.
    """

    adds: list[C] = field(default_factory=list)
    updates: list[tuple[LiveTrustObject, C]] = field(default_factory=list)
    deletes: list[LiveTrustObject] = field(default_factory=list)
    unmanaged: list[LiveTrustObject] = field(default_factory=list)
    locked: list[tuple[C, LiveTrustObject | None]] = field(default_factory=list)
    blocked: list[tuple[LiveTrustObject, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def _refids_by_name(
    type_name: str, resources: list[ResourceConfig], live: list[LiveTrustObject]
) -> dict[str, str]:
    """Map each ``type_name`` resource name to the ``refid`` of its live row."""
    refid_by_descr = {row.description: row.refid for row in live if row.refid}
    result: dict[str, str] = {}
    for resource in resources:
        if resource.type != type_name:
            continue
        description = description_of(resource.name, resource.config)
        refid = refid_by_descr.get(description)
        if refid:
            result[resource.name] = refid
    return result


def ca_refids_by_name(
    ca_resources: list[ResourceConfig], live_cas: list[LiveTrustObject]
) -> dict[str, str]:
    """Map each managed CA resource name to the ``refid`` of its live row.

    Reusable lookup for anything that holds a ``ca_ref`` (the certificates here,
    the OpenVPN instances in #808). A CA with no live row, or a live row with no
    ``refid``, is left out of the result.

    Args:
        ca_resources: ``trust.cas`` resources (secrets need not be resolved).
        live_cas: Live CA rows from :meth:`TrustService.search_cas`.

    Returns:
        ``{resource_name: refid}``.
    """
    return _refids_by_name("trust.cas", ca_resources, live_cas)


def cert_refids_by_name(
    cert_resources: list[ResourceConfig], live_certs: list[LiveTrustObject]
) -> dict[str, str]:
    """Map each managed certificate resource name to the ``refid`` of its live row.

    Counterpart of :func:`ca_refids_by_name` for anything that holds a ``cert_ref``
    (the OpenVPN instances, #1320). A certificate with no live row, or a live row
    with no ``refid``, is left out of the result.

    Args:
        cert_resources: ``trust.certs`` resources (secrets need not be resolved).
        live_certs: Live certificate rows from :meth:`TrustService.search_certs`.

    Returns:
        ``{resource_name: refid}``.
    """
    return _refids_by_name("trust.certs", cert_resources, live_certs)


def compute_diff[C: (TrustCaConfig, TrustCertConfig)](
    desired: list[C],
    current: list[LiveTrustObject],
    *,
    kind: TrustKind,
    add_only: bool = False,
    managed_keys: set[str] | None = None,
    ca_refids: Mapping[str, str] | None = None,
) -> Diff[C]:
    """Compare desired YAML state to live state, keyed by description.

    Args:
        desired: Objects the operator wants to exist.
        current: Objects currently on the box.
        kind: ``"ca"`` or ``"cert"``; selects the delete guards.
        add_only: If True, never emit deletes.
        managed_keys: When given, only live objects whose description is in this set
            may be deleted; others go to ``Diff.unmanaged`` (ADR-0018).
        ca_refids: ``ca_ref`` name to live ``refid``, used to compare a certificate's
            ``caref``. A ``ca_ref`` missing from it is not compared.

    Returns:
        The diff. Live objects that would be deleted but are in use (or, for CAs,
        look ACME-issued) are in ``blocked`` instead of ``deletes``.

    Raises:
        OpnsenseDriftError: If two live objects share a description.
    """
    current_by_key: dict[str, LiveTrustObject] = {}
    for live in current:
        if live.diff_key in current_by_key:
            raise OpnsenseDriftError(
                f"trust {kind}: more than one live object has description "
                f"{live.diff_key!r}; rename one on the box before planning"
            )
        current_by_key[live.diff_key] = live
    desired_by_key: dict[str, C] = {c.diff_key: c for c in desired}
    locked_keys = {c.diff_key for c in desired if c.lock}
    refids = ca_refids or {}

    diff: Diff[C] = Diff()
    for key, want in desired_by_key.items():
        have = current_by_key.get(key)
        if want.lock:
            diff.locked.append((want, have))
            continue
        if have is None:
            diff.adds.append(want)
        elif _needs_update(have, want, refids):
            diff.updates.append((have, want))

    if add_only:
        return diff
    for key, have in current_by_key.items():
        if key in locked_keys or key in desired_by_key:
            continue
        if managed_keys is not None and key not in managed_keys:
            diff.unmanaged.append(have)
            continue
        reason = _delete_block_reason(have, kind)
        if reason:
            diff.blocked.append((have, reason))
            diff.warnings.append(f"trust {kind} {key!r} kept: {reason}")
            continue
        diff.deletes.append(have)
    return diff


def _delete_block_reason(live: LiveTrustObject, kind: TrustKind) -> str:
    """Return why a live object must not be deleted, or an empty string."""
    if live.in_use:
        return "the box reports it in use"
    if kind == "ca" and is_acme_issued_descr(live.description):
        return "it looks issued by the AcmeClient plugin"
    return ""


def _needs_update(have: LiveTrustObject, want: TrustConfig, ca_refids: Mapping[str, str]) -> bool:
    """Return True if the live object differs from the desired one.

    ``crt`` always compares. ``prv`` and ``csr`` compare only when both sides
    are non-empty, because the box may not return them. ``type`` is not compared.
    """
    if normalize_pem(have.crt) != normalize_pem(want.crt):
        return True
    if want.prv and have.prv and normalize_pem(have.prv) != normalize_pem(want.prv):
        return True
    if isinstance(want, TrustCertConfig):
        if want.csr and have.csr and normalize_pem(have.csr) != normalize_pem(want.csr):
            return True
        wanted_caref = ca_refids.get(want.ca_ref, "") if want.ca_ref else ""
        if wanted_caref and have.caref != wanted_caref:
            return True
    return False


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------

_CA_KEYS = frozenset({"description", "crt", "prv", "lock"})
_CERT_KEYS = frozenset({"description", "crt", "prv", "csr", "ca_ref", "type", "lock"})


def description_of(name: str, config: Mapping[str, Any]) -> str:
    """Return the identity description of a resource.

    Args:
        name: Resource name, the fallback.
        config: Resource config.

    Returns:
        ``description`` when a non-empty string, else ``name``.
    """
    description = config.get("description")
    if isinstance(description, str) and description:
        return description
    return name


def _str_field(config: Mapping[str, Any], key: str, label: str, name: str) -> str:
    value = config.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{label} '{name}' {key} must be a string")
    return value


def _bool_field(config: Mapping[str, Any], key: str, label: str, name: str) -> bool:
    value = config.get(key, False)
    if not isinstance(value, bool):
        raise ValueError(f"{label} '{name}' {key} must be a boolean (true/false)")
    return value


def _check_pem(value: str, key: str, label: str, name: str, *, private: bool = False) -> None:
    """Raise if a resolved PEM field lacks markers. Never echoes the value."""
    if not value:
        return
    if not has_pem_markers(value):
        raise ValueError(f"{label} '{name}' {key} is not PEM (no BEGIN/END markers)")
    if private and not any(m in value for m in _PRIVATE_KEY_MARKERS):
        raise ValueError(f"{label} '{name}' {key} is not a PEM private key")


def trust_ca_configs_from_resources(
    resources: list[ResourceConfig], *, require_pem: bool = False
) -> list[TrustCaConfig]:
    """Convert ``trust.cas`` resources to :class:`TrustCaConfig`.

    Args:
        resources: Provider resources; other types are skipped.
        require_pem: Check PEM markers on ``crt`` and ``prv``. Use True only after
            secret resolution; unresolved ``secret://`` URIs are not PEM.

    Returns:
        The configs.

    Raises:
        ValueError: On a non-dict config, a missing ``crt``, a wrong field type or
            (with ``require_pem``) a non-PEM value. The message names the resource,
            never a field value.
    """
    configs: list[TrustCaConfig] = []
    for resource in resources:
        if resource.type != "trust.cas":
            continue
        label, name, config = "trust_ca", resource.name, resource.config
        if not isinstance(config, dict):
            raise ValueError(f"{label} '{name}' has non-dict config")
        crt = _str_field(config, "crt", label, name)
        if not crt:
            raise ValueError(f"{label} '{name}' requires a non-empty 'crt'")
        prv = _str_field(config, "prv", label, name)
        description = _str_field(config, "description", label, name) or name
        lock = _bool_field(config, "lock", label, name)
        if require_pem:
            _check_pem(crt, "crt", label, name)
            _check_pem(prv, "prv", label, name, private=True)
        configs.append(
            TrustCaConfig(name=name, description=description, crt=crt, prv=prv, lock=lock)
        )
    return configs


def trust_cert_configs_from_resources(
    resources: list[ResourceConfig], *, require_pem: bool = False
) -> list[TrustCertConfig]:
    """Convert ``trust.certs`` resources to :class:`TrustCertConfig`.

    Args:
        resources: Provider resources; other types are skipped.
        require_pem: Check PEM markers on ``crt``, ``prv`` and ``csr``. Use True only
            after secret resolution.

    Returns:
        The configs.

    Raises:
        ValueError: On a non-dict config, a missing ``crt``, a wrong field type, an
            invalid ``type`` or (with ``require_pem``) a non-PEM value. The message
            names the resource, never a field value.
    """
    configs: list[TrustCertConfig] = []
    for resource in resources:
        if resource.type != "trust.certs":
            continue
        label, name, config = "trust_cert", resource.name, resource.config
        if not isinstance(config, dict):
            raise ValueError(f"{label} '{name}' has non-dict config")
        crt = _str_field(config, "crt", label, name)
        if not crt:
            raise ValueError(f"{label} '{name}' requires a non-empty 'crt'")
        prv = _str_field(config, "prv", label, name)
        csr = _str_field(config, "csr", label, name)
        ca_ref = _str_field(config, "ca_ref", label, name)
        cert_type = _str_field(config, "type", label, name)
        if cert_type and cert_type not in CERT_TYPE_WIRE:
            raise ValueError(f"{label} '{name}' type must be one of {list(ALLOWED_CERT_TYPES)}")
        description = _str_field(config, "description", label, name) or name
        lock = _bool_field(config, "lock", label, name)
        if require_pem:
            _check_pem(crt, "crt", label, name)
            _check_pem(prv, "prv", label, name, private=True)
            _check_pem(csr, "csr", label, name)
        configs.append(
            TrustCertConfig(
                name=name,
                description=description,
                crt=crt,
                prv=prv,
                csr=csr,
                ca_ref=ca_ref,
                type=cert_type,
                lock=lock,
            )
        )
    return configs


# ---------------------------------------------------------------------------
# Row parsing
# ---------------------------------------------------------------------------


def _text(value: Any) -> str:
    """Stringify a scalar row value; ``None`` and containers become empty."""
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value)


def _row_pem(row: dict[str, Any], key: str) -> str:
    """Return a row's PEM: the raw ``<key>_payload``, else the decoded base64 ``<key>``."""
    payload = _text(row.get(f"{key}_payload"))
    if payload:
        return payload
    encoded = _text(row.get(key))
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded, validate=False).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return ""


def _row_to_live(row: dict[str, Any]) -> LiveTrustObject:
    """Normalize a ``search`` row into a :class:`LiveTrustObject`."""
    return LiveTrustObject(
        uuid=_text(row.get("uuid")),
        refid=_text(row.get("refid")),
        description=_text(row.get("descr")),
        caref=_text(row.get("caref")),
        in_use=_text(row.get("in_use")) in {"1", "True", "true"},
        crt=_row_pem(row, "crt"),
        prv=_row_pem(row, "prv"),
        csr=_row_pem(row, "csr"),
        raw=row,
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class TrustService(BaseService):
    """Service for OPNsense trust-store operations via direct API.

    There is no reconfigure step: the trust controllers save to ``config.xml``
    directly, so the managers declare no ``FINALIZATION_HOOK``.
    """

    @staticmethod
    def _crud(kind: TrustKind) -> endpoints.CrudEndpoints:
        return endpoints.TRUST_CA if kind == "ca" else endpoints.TRUST_CERT

    def _search(self, kind: TrustKind) -> list[LiveTrustObject]:
        spec = self._crud(kind).search
        response = self.client.request(spec.method, spec.path())
        rows: list[dict[str, Any]] = []
        if isinstance(response, dict):
            raw_rows = response.get("rows")
            if isinstance(raw_rows, list):
                rows = [r for r in raw_rows if isinstance(r, dict)]
        return [_row_to_live(row) for row in rows]

    def search_cas(self) -> list[LiveTrustObject]:
        """Fetch the live CAs."""
        return self._search("ca")

    def search_certs(self) -> list[LiveTrustObject]:
        """Fetch the live certificates."""
        return self._search("cert")

    def add(self, kind: TrustKind, config: TrustConfig, caref: str = "") -> dict[str, Any]:
        """Create a CA or certificate.

        Args:
            kind: ``"ca"`` or ``"cert"``.
            config: Desired object.
            caref: Resolved signing-CA ``refid`` (certificates only).

        Returns:
            The API response.

        Raises:
            APIError: If the box rejects the write.
        """
        spec = self._crud(kind).add
        response = self.client.request(
            spec.method, spec.path(), data=config.to_payload(caref=caref)
        )
        raise_on_failed_write(response, f"add trust {kind} {config.name!r}")
        return response

    def update(
        self, kind: TrustKind, uuid: str, config: TrustConfig, caref: str = ""
    ) -> dict[str, Any]:
        """Update a CA or certificate by UUID.

        Args:
            kind: ``"ca"`` or ``"cert"``.
            uuid: Row UUID.
            config: New desired object.
            caref: Resolved signing-CA ``refid`` (certificates only).

        Returns:
            The API response.

        Raises:
            APIError: If the box rejects the write.
        """
        spec = self._crud(kind).update
        response = self.client.request(
            spec.method, spec.path(uuid=uuid), data=config.to_payload(caref=caref)
        )
        raise_on_failed_write(response, f"update trust {kind} {config.name!r}")
        return response

    def delete(self, kind: TrustKind, uuid: str, label: str) -> dict[str, Any]:
        """Delete a CA or certificate by UUID.

        Args:
            kind: ``"ca"`` or ``"cert"``.
            uuid: Row UUID.
            label: Description to name the object in an error.

        Returns:
            The API response.

        Raises:
            APIError: If the box refuses the delete.
        """
        spec = self._crud(kind).delete
        response = self.client.request(spec.method, spec.path(uuid=uuid))
        raise_on_failed_write(response, f"delete trust {kind} {label!r}")
        return response

    def apply_diff(
        self,
        diff: Diff[Any],
        *,
        kind: TrustKind,
        ca_refids: Mapping[str, str] | None = None,
    ) -> dict[str, int]:
        """Dispatch the operations in ``diff``.

        Args:
            diff: The diff to apply.
            kind: ``"ca"`` or ``"cert"``.
            ca_refids: ``ca_ref`` name to live ``refid`` (certificates only).

        Returns:
            ``{"created": N, "updated": M, "deleted": K}``.

        Raises:
            ReferenceValidationError: If a certificate's ``ca_ref`` has no live CA.
                Checked before any write.
        """
        refids = ca_refids or {}
        carefs: dict[str, str] = {}
        for config in [*diff.adds, *(want for _, want in diff.updates)]:
            ca_ref = getattr(config, "ca_ref", "")
            if not ca_ref:
                continue
            if ca_ref not in refids:
                raise ReferenceValidationError(
                    f"trust_cert '{config.name}' ca_ref '{ca_ref}' does not match any "
                    f"live CA; apply the trust.cas resource first"
                )
            carefs[config.name] = refids[ca_ref]

        created = updated = deleted = 0
        for config in diff.adds:
            self.add(kind, config, carefs.get(config.name, ""))
            created += 1
        for live, want in diff.updates:
            self.update(kind, live.uuid, want, carefs.get(want.name, ""))
            updated += 1
        for live in diff.deletes:
            self.delete(kind, live.uuid, live.description)
            deleted += 1
        return {"created": created, "updated": updated, "deleted": deleted}
