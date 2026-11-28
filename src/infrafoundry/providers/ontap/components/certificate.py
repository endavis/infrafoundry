"""Install an ACME certificate on a NetApp ONTAP cluster or SVM over REST (#1684).

Order, chosen so that a failure never locks InfraFoundry out of the cluster: install the
leaf, key and chain (``POST /api/security/certificates``), bind the certificate to the web
service, wait until the cluster answers on the new leaf, check what it serves, and only then
delete the superseded certificates this module installed earlier. Binding the cluster web
service restarts it and breaks the session, so everything after the bind uses a client pinned
to the new leaf's SHA-256. A failed check binds the previous certificate again. Messages never
carry PEM text.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import replace
from typing import cast

from cryptography import x509
from cryptography.x509.oid import NameOID

from infrafoundry.core.certs.install import (
    CertificateTarget,
    TargetEndpoint,
    served_chain_validates,
    verify_served,
)
from infrafoundry.core.certs.keys import describe
from infrafoundry.core.certs.models import CertificateError, CertificateInstallError
from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.providers._netapp.ontap import (
    ConnectionParams,
    OntapAPIError,
    OntapCertificateService,
    OntapConnectionError,
    connect_ontap,
)

from ..settings import OntapSettings

logger = logging.getLogger(__name__)

_PEM_RE = re.compile(r"-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----", re.DOTALL)
_CERT_RE = re.compile(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.DOTALL)
_SLUG_RE = re.compile(r"[^A-Za-z0-9_.-]")
_SHA_LEN = 12
_MIN_SECRET_LINE = 16
BIND_WINDOW_SECONDS = 120.0
BIND_INTERVAL_SECONDS = 3.0

ServiceFactory = Callable[[ConnectionParams], OntapCertificateService]
Verifier = Callable[[CertificateTarget, str], None]
Validates = Callable[[str, int, str], bool]
"""``(address, port, server_name) -> True`` when the served leaf passes default validation."""


def connect_certificate_service(params: ConnectionParams) -> OntapCertificateService:
    """Connect to the cluster; the real service implements the certificate calls too."""
    return cast(OntapCertificateService, connect_ontap(params))


class OntapCertificateInstaller:
    """Installs one certificate on one ONTAP cluster (or on one of its SVMs)."""

    def __init__(
        self,
        settings: OntapSettings,
        service: OntapCertificateService | None = None,
        *,
        service_factory: ServiceFactory = connect_certificate_service,
        verify: Verifier = lambda target, sha: verify_served(target, sha),
        validates: Validates = served_chain_validates,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        bind_window: float = BIND_WINDOW_SECONDS,
        interval: float = BIND_INTERVAL_SECONDS,
    ) -> None:
        """Initialize the installer.

        Args:
            settings: Connection settings of the cluster.
            service: The REST service; built from ``settings`` when omitted.
            service_factory: Builds a service from connection parameters (the pinned and the
                validating clients after the bind).
            verify: Checks the served certificate; ``verify_served`` by default.
            validates: Tells whether the served certificate passes default TLS validation.
            sleep: Sleep function.
            monotonic: Clock for the bind window.
            bind_window: Seconds to wait for the cluster to answer on the new certificate.
            interval: Seconds between attempts.
        """
        self._settings = settings
        self._params = settings.connection_params()
        self._factory = service_factory
        self._service: OntapCertificateService = service or service_factory(self._params)
        self._verify = verify
        self._validates = validates
        self._sleep = sleep
        self._monotonic = monotonic
        self._bind_window = bind_window
        self._interval = interval

    def install(
        self, target: CertificateTarget, cert_pem: str, chain_pem: str, key_pem: str
    ) -> None:
        """Install the certificate and key, bind them and verify what is served.

        Args:
            target: The resolved target; ``kind`` is ``cluster`` or ``svm``.
            cert_pem: The leaf certificate.
            chain_pem: The intermediate chain (may be empty).
            key_pem: The private key. Never logged.

        Raises:
            CertificateInstallError: On any failure. The message holds no PEM text.
        """
        secrets = (key_pem, cert_pem, chain_pem)
        where = f"svm '{target.svm}'" if target.kind == "svm" else "the cluster"
        try:
            self._install(target, cert_pem, chain_pem, key_pem)
        except CertificateInstallError as exc:
            raise CertificateInstallError(_scrub(str(exc), secrets)) from None
        except (InfraFoundryError, OSError) as exc:
            raise CertificateInstallError(
                f"installing on {where} failed: {_scrub(str(exc), secrets)}"
            ) from None

    # -- the steps ----------------------------------------------------------------------

    def _install(
        self, target: CertificateTarget, cert_pem: str, chain_pem: str, key_pem: str
    ) -> None:
        try:
            sha = describe(cert_pem).sha256
            common_name = _common_name(cert_pem)
        except CertificateError as exc:
            raise CertificateInstallError(str(exc)) from None
        svm = target.svm if target.kind == "svm" else None
        prefix = _name_prefix(svm)
        name = f"{prefix}{sha[:_SHA_LEN]}"
        svm_uuid = self._service.svm_uuid(svm) if svm else None
        previous = self._service.web_certificate_uuid(svm_uuid)
        new_uuid, created = self._ensure_certificate(
            name, svm, common_name, cert_pem, chain_pem, key_pem, sha
        )
        if previous == new_uuid:
            logger.info("%s is already bound; verifying it", name)
            self._check_served(target, sha, svm)
            self._remove_superseded(self._service, svm, prefix, name, new_uuid)
            self._warn_if_unvalidated(target, svm)
            return
        service = self._bind(new_uuid, created, previous, svm_uuid, sha)
        try:
            self._check_served(target, sha, svm)
        except CertificateInstallError as exc:
            raise self._roll_back(exc, service, new_uuid, previous, svm_uuid, name) from None
        self._remove_superseded(service, svm, prefix, name, new_uuid)
        self._warn_if_unvalidated(target, svm)

    def _ensure_certificate(
        self,
        name: str,
        svm: str | None,
        common_name: str,
        cert_pem: str,
        chain_pem: str,
        key_pem: str,
        sha: str,
    ) -> tuple[str, bool]:
        """Reuse the same-named certificate when it holds this leaf, else install it."""
        existing = self._service.find_certificate(name, svm)
        if existing is not None:
            try:
                held = describe(str(existing.get("public_certificate", ""))).sha256
            except CertificateError:
                held = ""
            if held != sha or not existing.get("uuid"):
                raise CertificateInstallError(
                    f"a certificate named '{name}' already exists on the cluster with different "
                    "content; delete it on the console and run 'foundry certs issue' again"
                )
            return str(existing["uuid"]), False
        uuid = self._service.install_certificate(
            name=name,
            common_name=common_name,
            public_certificate=cert_pem,
            private_key=key_pem,
            intermediates=_CERT_RE.findall(chain_pem),
            svm=svm,
        )
        return uuid, True

    def _bind(
        self, new_uuid: str, created: bool, previous: str | None, svm_uuid: str | None, sha: str
    ) -> OntapCertificateService:
        """Bind the certificate and return the service to use from here on."""
        try:
            self._service.bind_web_certificate(new_uuid, svm_uuid)
        except OntapConnectionError:
            if svm_uuid:
                self._delete_new(created, new_uuid)
                raise
            # The cluster web service restarts on the new certificate and drops the session.
            logger.info("connection closed while binding the certificate; waiting for it")
        except OntapAPIError:
            self._delete_new(created, new_uuid)
            raise
        if svm_uuid:
            return self._service
        pinned = self._factory(_pinned_params(self._params, sha))
        self._wait_for_bind(pinned, new_uuid, created, previous)
        return pinned

    def _wait_for_bind(
        self,
        pinned: OntapCertificateService,
        new_uuid: str,
        created: bool,
        previous: str | None,
    ) -> None:
        deadline = self._monotonic() + self._bind_window
        last = "no attempt was made"
        while True:
            try:
                if pinned.web_certificate_uuid(None) == new_uuid:
                    return
                last = "the cluster still uses another certificate"
            except InfraFoundryError as exc:
                last = f"the cluster does not answer yet: {exc.__class__.__name__}"
            if self._monotonic() >= deadline:
                break
            self._sleep(self._interval)
        self._give_up_waiting(new_uuid, created, previous, last)

    def _give_up_waiting(
        self, new_uuid: str, created: bool, previous: str | None, last: str
    ) -> None:
        """Clean up after a bind that never took effect, then raise."""
        try:
            still_previous = self._service.web_certificate_uuid(None) == previous
        except InfraFoundryError:
            still_previous = False
        if still_previous:
            self._delete_new(created, new_uuid)
            raise CertificateInstallError(
                f"the cluster did not switch to the new certificate within "
                f"{self._bind_window:.0f}s ({last}); the previous certificate is still in use "
                "and the new one was removed"
            )
        raise CertificateInstallError(
            f"the cluster did not answer on the new certificate within {self._bind_window:.0f}s "
            f"({last}). The new certificate (uuid {new_uuid}) may be bound, the previous one "
            f"was {previous or 'none'}. Check the web service certificate on the cluster console"
        )

    def _check_served(self, target: CertificateTarget, sha: str, svm: str | None) -> None:
        """Check the endpoint serves the new leaf and that the validating client can use it."""
        address = target.endpoint.address if target.endpoint else self._settings.host
        port = target.verify_port or 443
        server_name = target.verify_server_name
        if not server_name:
            raise CertificateInstallError("the target has no verify.server_name")
        try:
            self._verify(
                replace(
                    target,
                    endpoint=TargetEndpoint(address=address),
                    verify_port=port,
                    verify_server_name=server_name,
                ),
                sha,
            )
            production = self._validates(address, port, server_name)
        except OSError as exc:
            raise CertificateInstallError(
                f"checking what '{address}' serves failed: {exc.__class__.__name__}"
            ) from None
        if not production or svm:
            return  # staging, or an SVM certificate: the cluster client is unaffected
        validating = self._factory(
            replace(
                self._params,
                tls_server_name=server_name,
                fingerprint=None,
                ca_bundle=None,
                verify_ssl=None,
            )
        )
        try:
            validating.cluster_info()
        except InfraFoundryError as exc:
            raise CertificateInstallError(
                f"the cluster serves the new certificate but the validating client failed: {exc}"
            ) from None

    def _roll_back(
        self,
        cause: CertificateInstallError,
        service: OntapCertificateService,
        new_uuid: str,
        previous: str | None,
        svm_uuid: str | None,
        name: str,
    ) -> CertificateInstallError:
        """Bind the previous certificate again and delete the new one; return the error."""
        console = (
            f"the new certificate '{name}' is installed and bound"
            + (", the previous one could not be restored" if previous else "")
            + "; restore a working certificate for the web service on the cluster console "
            "(the 'security ssl' commands)"
        )
        if previous is None:
            return CertificateInstallError(f"{cause}; {console}")
        try:
            try:
                service.bind_web_certificate(previous, svm_uuid)
            except OntapConnectionError:
                if svm_uuid:
                    raise
            if not svm_uuid:
                self._wait_for_original(previous)
            self._service.delete_certificate(new_uuid)
        except (InfraFoundryError, CertificateInstallError) as exc:
            return CertificateInstallError(
                f"{cause}; rolling back to certificate {previous} failed ({exc}); {console}"
            )
        return CertificateInstallError(
            f"{cause}; the previous certificate is bound again and the new one was removed"
        )

    def _wait_for_original(self, previous: str) -> None:
        """Wait until the original client sees the previous certificate bound again."""
        deadline = self._monotonic() + self._bind_window
        while True:
            try:
                if self._service.web_certificate_uuid(None) == previous:
                    return
            except InfraFoundryError:
                pass
            if self._monotonic() >= deadline:
                raise CertificateInstallError(
                    "the cluster did not return to the previous certificate in time"
                )
            self._sleep(self._interval)

    def _remove_superseded(
        self,
        service: OntapCertificateService,
        svm: str | None,
        prefix: str,
        name: str,
        bound_uuid: str,
    ) -> None:
        """Delete the earlier certificates this module installed that nothing uses now.

        Only ``type: server`` certificates of this scope named ``<prefix><sha prefix>`` are
        candidates: trust anchors (``server_ca``) and foreign certificates are never touched.
        """
        pattern = re.compile(rf"^{re.escape(prefix)}[0-9a-f]{{{_SHA_LEN}}}$")
        try:
            rows = service.list_server_certificates(svm)
        except InfraFoundryError as exc:
            logger.warning("could not list superseded certificates: %s", exc)
            return
        for row in rows:
            row_name = str(row.get("name", ""))
            if (
                row.get("type", "server") != "server"
                or not pattern.fullmatch(row_name)
                or row_name == name
                or row.get("uuid") in (None, "", bound_uuid)
            ):
                continue
            if svm is None and row.get("scope", "cluster") != "cluster":
                continue
            try:
                service.delete_certificate(str(row["uuid"]))
            except InfraFoundryError as exc:
                logger.warning("could not delete superseded certificate %s: %s", row_name, exc)

    def _warn_if_unvalidated(self, target: CertificateTarget, svm: str | None) -> None:
        """Say how to re-pin after a staging certificate (it cannot pass CA validation)."""
        if svm or self._settings.fingerprint is None or self._settings.tls_server_name:
            return
        address = self._settings.host
        server_name = target.verify_server_name or ""
        try:
            production = self._validates(address, target.verify_port or 443, server_name)
        except OSError:
            return
        if production:
            return
        logger.warning(
            "the cluster now serves a certificate that does not pass CA validation (a staging "
            "or custom directory); the configured tls_fingerprint is stale. Re-pin "
            "provider_settings.ontap.tls_fingerprint to the new certificate's SHA-256 "
            "fingerprint before the next plan or apply"
        )

    def _delete_new(self, created: bool, uuid: str) -> None:
        if not created:
            return
        try:
            self._service.delete_certificate(uuid)
        except InfraFoundryError:
            logger.warning("could not delete the new certificate %s", uuid)


def _pinned_params(params: ConnectionParams, sha: str) -> ConnectionParams:
    """Connection parameters that trust exactly the certificate with this SHA-256."""
    return replace(params, fingerprint=sha, ca_bundle=None, verify_ssl=None, tls_server_name=None)


def _name_prefix(svm: str | None) -> str:
    return f"infrafoundry-svm-{_SLUG_RE.sub('-', svm)}-" if svm else "infrafoundry-cluster-"


def _common_name(cert_pem: str) -> str:
    """Return the subject common name, or else the first DNS name (ONTAP insists on one)."""
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise CertificateError("the certificate is not a valid PEM certificate") from None
    for attribute in cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME):
        value = attribute.value
        if isinstance(value, str) and value:
            return value
    names = describe(cert_pem).names
    if not names:
        raise CertificateError("the certificate has neither a common name nor a DNS name")
    return names[0]


def _scrub(text: str, secrets: tuple[str, ...]) -> str:
    """Remove PEM blocks and every line of the key, certificate and chain from a message."""
    text = _PEM_RE.sub("", text)
    secret_lines = {ln.strip() for pem in secrets for ln in pem.splitlines() if ln.strip()}
    for line in secret_lines:
        if len(line) >= _MIN_SECRET_LINE:
            text = text.replace(line, "")
    return "\n".join(
        ln for ln in text.splitlines() if ln.strip() not in secret_lines and "PRIVATE" not in ln
    )
