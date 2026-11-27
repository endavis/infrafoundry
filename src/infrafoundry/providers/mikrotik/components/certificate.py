"""Install an ACME certificate on a RouterOS device over its REST API (#1683).

Order, chosen so that a failure never locks InfraFoundry out of the device: upload the
PEM files, import them, check the imported certificate holds its private key, rename the
rows, delete the uploaded files, point ``api-ssl`` and ``www-ssl`` at the new certificate,
check what the device now serves, and only then delete the superseded certificates this
module installed earlier. A device-side API error rolls back; messages never carry PEM text.
"""

from __future__ import annotations

import logging
import re
import socket
import ssl
from collections.abc import Callable
from dataclasses import replace
from typing import Any, Protocol

from infrafoundry.core.certs.install import CertificateTarget, TargetEndpoint, verify_served
from infrafoundry.core.certs.keys import describe
from infrafoundry.core.certs.models import CertificateError, CertificateInstallError
from infrafoundry.core.exceptions import InfraFoundryError

from ..client import RouterOSAPIError, RouterOSClient, RouterOSConnectionError, RouterOSWriter
from ..settings import MikroTikSettings, management_host

logger = logging.getLogger(__name__)

SERVICES = ("api-ssl", "www-ssl")
"""The RouterOS services that serve the installed certificate, in the order they are patched."""

_PEM_RE = re.compile(r"-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----", re.DOTALL)
_CERT_RE = re.compile(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.DOTALL)
_SLUG_RE = re.compile(r"[^A-Za-z0-9_.-]")
_SHA_LEN = 12
_INSTALLED_NAME = re.compile(rf"^infrafoundry-.+-[0-9a-f]{{{_SHA_LEN}}}(-ca\d+)?$")


def is_installed_certificate_name(name: str) -> bool:
    """Return whether ``name`` follows the ``infrafoundry-<slug>-<sha prefix>`` scheme."""
    return _INSTALLED_NAME.fullmatch(name) is not None


class CertificateClient(RouterOSWriter, Protocol):
    """What the installer needs from a RouterOS client: the writer plus action calls."""

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """Call an action endpoint and return the decoded reply."""
        ...


Validates = Callable[[str, int, str], bool]
"""``(address, port, server_name) -> True`` when the served leaf passes default validation."""

Verifier = Callable[[CertificateTarget, str], None]


def served_chain_validates(address: str, port: int, server_name: str) -> bool:
    """Return whether the endpoint's certificate passes the default TLS validation.

    A Let's Encrypt production certificate does; a staging or custom-directory one does not.

    Args:
        address: Host or IP to connect to.
        port: TCP port.
        server_name: Host name for SNI and the host name check.

    Raises:
        OSError: If the endpoint cannot be reached.
    """
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        with (
            socket.create_connection((address, port), timeout=10) as sock,
            context.wrap_socket(sock, server_hostname=server_name),
        ):
            return True
    except ssl.SSLCertVerificationError:
        return False


class RouterOSCertificateInstaller:
    """Installs one certificate on one RouterOS device."""

    def __init__(
        self,
        settings: MikroTikSettings,
        client: CertificateClient | None = None,
        *,
        client_factory: Callable[[MikroTikSettings], CertificateClient] = RouterOSClient,
        verify: Verifier = lambda target, sha: verify_served(target, sha),
        validates: Validates = served_chain_validates,
    ) -> None:
        """Initialize the installer.

        Args:
            settings: Connection settings of the device (an ``https`` ``api_url``).
            client: The REST client; built from ``settings`` when omitted.
            client_factory: Builds a client from settings (the validating one after install).
            verify: Checks the served certificate; ``verify_served`` by default.
            validates: Tells whether the served certificate passes default TLS validation.
        """
        self._settings = settings
        self._client: CertificateClient = client or client_factory(settings)
        self._client_factory = client_factory
        self._verify = verify
        self._validates = validates

    def install(
        self, target: CertificateTarget, cert_pem: str, chain_pem: str, key_pem: str
    ) -> None:
        """Install the certificate and key, activate them and verify what is served.

        Args:
            target: The resolved target; ``resource`` names the ``ip.service`` resource.
            cert_pem: The leaf certificate.
            chain_pem: The intermediate chain (may be empty).
            key_pem: The private key. Never logged.

        Raises:
            CertificateInstallError: On any failure. The message holds no PEM text.
        """
        if self._settings.scheme != "https":
            raise CertificateInstallError(
                "the private key would travel in plaintext: set provider_settings.mikrotik."
                "api_url to an https URL before installing a certificate"
            )
        secrets = (key_pem, cert_pem, chain_pem)
        try:
            self._install(target, cert_pem, chain_pem, key_pem)
        except CertificateInstallError as exc:
            raise CertificateInstallError(_scrub(str(exc), secrets)) from None
        except (InfraFoundryError, OSError) as exc:
            raise CertificateInstallError(
                f"installing on '{target.resource}' failed: {_scrub(str(exc), secrets)}"
            ) from None

    # -- the steps ----------------------------------------------------------------------

    def _install(
        self, target: CertificateTarget, cert_pem: str, chain_pem: str, key_pem: str
    ) -> None:
        try:
            sha = describe(cert_pem).sha256
        except CertificateError as exc:
            raise CertificateInstallError(str(exc)) from None
        slug = _slug(target.resource)
        base = f"infrafoundry-{slug}-{sha[:_SHA_LEN]}"
        services = self._services()
        existing = {row[".id"] for row in self._client.get("certificate")}
        files = self._upload_and_import(base, cert_pem, chain_pem, key_pem)
        imported: list[str] = []
        try:
            imported = self._name_rows(base, sha, chain_pem, existing)
        except (CertificateInstallError, InfraFoundryError):
            self._delete_rows(self._new_ids(existing))
            self._remove_files(files, strict=False)
            raise
        self._remove_files(files, strict=True)
        previous = {name: services[name][1] for name in SERVICES}
        self._activate(base, services, previous, imported, target)
        old = previous.get("www-ssl") or "none"
        try:
            self._check_served(target, sha)
        except CertificateInstallError as exc:
            raise CertificateInstallError(
                f"{exc}; the new certificate '{base}' is installed and assigned, the previous "
                f"one was '{old}'. To go back, run on the device console: "
                f"'/ip service set api-ssl,www-ssl certificate={old}'"
            ) from None
        self._remove_superseded(slug, base)

    def _services(self) -> dict[str, tuple[str, str]]:
        """Return ``{service: (.id, certificate)}`` for the services that get the certificate."""
        rows = {row.get("name", ""): row for row in self._client.get("ip/service")}
        missing = [name for name in SERVICES if name not in rows]
        if missing:
            raise CertificateInstallError(f"the device has no ip service: {', '.join(missing)}")
        return {n: (rows[n][".id"], rows[n].get("certificate", "")) for n in SERVICES}

    def _upload_and_import(
        self, base: str, cert_pem: str, chain_pem: str, key_pem: str
    ) -> list[str]:
        """Upload the PEM files and import them (leaf, key, chain). Returns the file names."""
        leaf, key, chain = f"{base}-leaf.crt", f"{base}-key.key", f"{base}-chain.crt"
        uploads = [(leaf, cert_pem), (key, key_pem)]
        if chain_pem.strip():
            uploads.append((chain, chain_pem))
        names: list[str] = []
        try:
            for name, contents in uploads:
                names.append(name)
                self._client.put("file", {"name": name, "contents": contents})
            for name, _ in uploads:
                # Unencrypted PEM: the passphrase argument is optional and omitted.
                self._client.post("certificate/import", {"file-name": name})
        except (CertificateInstallError, InfraFoundryError):
            self._remove_files(names, strict=False)
            raise
        return names

    def _name_rows(self, base: str, sha: str, chain_pem: str, existing: set[str]) -> list[str]:
        """Rename the imported leaf and chain rows; return the ids of every row to keep."""
        rows = self._client.get("certificate")
        leaves = [r for r in rows if _fingerprint(r) == sha]
        if not leaves:
            raise CertificateInstallError("RouterOS did not import the certificate")
        leaf = next((r for r in leaves if r.get("private-key") == "true"), None)
        if leaf is None:
            raise CertificateInstallError(
                "RouterOS imported the certificate without its private key"
            )
        self._rename(leaf, base)
        keep = [leaf[".id"]]
        for index, pem in enumerate(_CERT_RE.findall(chain_pem)):
            fingerprint = describe(pem).sha256
            match = next((r for r in rows if _fingerprint(r) == fingerprint), None)
            if match is not None:
                self._rename(match, f"{base}-ca{index}")
                keep.append(match[".id"])
        return keep

    def _rename(self, row: dict[str, str], name: str) -> None:
        if row.get("name") != name:
            self._client.patch("certificate", row[".id"], {"name": name})

    def _activate(
        self,
        base: str,
        services: dict[str, tuple[str, str]],
        previous: dict[str, str],
        imported: list[str],
        target: CertificateTarget,
    ) -> None:
        """Point the services at the new certificate; roll back on a device-side error."""
        done: list[str] = []
        for name in SERVICES:
            try:
                self._client.patch("ip/service", services[name][0], {"certificate": base})
            except RouterOSConnectionError:
                if name != SERVICES[-1]:
                    self._roll_back(services, previous, done, imported)
                    raise
                # The service restarts on the new certificate and drops the connection.
                logger.info("connection closed while switching %s; verifying", name)
            except RouterOSAPIError:
                self._roll_back(services, previous, done, imported)
                raise
            done.append(name)

    def _roll_back(
        self,
        services: dict[str, tuple[str, str]],
        previous: dict[str, str],
        done: list[str],
        imported: list[str],
    ) -> None:
        for name in reversed(done):
            try:
                self._client.patch("ip/service", services[name][0], {"certificate": previous[name]})
            except InfraFoundryError:
                logger.warning("could not restore the certificate of service %s", name)
        self._delete_rows(imported)

    def _check_served(self, target: CertificateTarget, sha: str) -> None:
        """Check the device serves the new leaf and that the validating client can use it."""
        address = management_host(self._settings.api_url)
        port = target.verify_port or self._settings.port
        server_name = target.verify_server_name
        if not server_name:
            raise CertificateInstallError("the target has no verify.server_name")
        self._verify(
            replace(
                target,
                endpoint=TargetEndpoint(address=address),
                verify_port=port,
                verify_server_name=server_name,
            ),
            sha,
        )
        if not self._validates(address, port, server_name):
            return  # staging or custom directory: the client keeps its verify_ssl setting
        validating = self._client_factory(replace(self._settings, tls_server_name=server_name))
        try:
            validating.get("system/resource")
        except InfraFoundryError as exc:
            raise CertificateInstallError(
                f"the device serves the new certificate but the validating client failed: {exc}"
            ) from None

    def _remove_superseded(self, slug: str, base: str) -> None:
        """Delete the earlier certificates this module installed that nothing uses now."""
        pattern = re.compile(rf"^infrafoundry-{re.escape(slug)}-[0-9a-f]{{{_SHA_LEN}}}(-ca\d+)?$")
        try:
            in_use = {r.get("certificate", "") for r in self._client.get("ip/service")}
            old = [
                r
                for r in self._client.get("certificate")
                if pattern.fullmatch(r.get("name", ""))
                and not r.get("name", "").startswith(base)
                and r.get("name", "") not in in_use
            ]
        except InfraFoundryError as exc:
            logger.warning("could not list superseded certificates: %s", exc)
            return
        self._delete_rows([r[".id"] for r in old])

    # -- helpers ------------------------------------------------------------------------

    def _new_ids(self, existing: set[str]) -> list[str]:
        try:
            return [r[".id"] for r in self._client.get("certificate") if r[".id"] not in existing]
        except InfraFoundryError:
            return []

    def _delete_rows(self, ids: list[str]) -> None:
        for row_id in ids:
            try:
                self._client.delete("certificate", row_id)
            except InfraFoundryError:
                logger.warning("could not delete certificate row %s", row_id)

    def _remove_files(self, names: list[str], *, strict: bool) -> None:
        """Delete the uploaded files. ``strict`` raises when one stays (the key file)."""
        try:
            rows = {r.get("name", ""): r[".id"] for r in self._client.get("file")}
        except InfraFoundryError as exc:
            if strict:
                raise CertificateInstallError(
                    f"could not list the uploaded files to remove them: {exc}"
                ) from None
            return
        left: list[str] = []
        for name in names:
            if name not in rows:
                continue
            try:
                self._client.delete("file", rows[name])
            except InfraFoundryError:
                left.append(name)
        if left and strict:
            raise CertificateInstallError(
                f"the uploaded file(s) {', '.join(left)} could not be removed from the device; "
                "delete them on the console (the key file holds the private key)"
            )


def _fingerprint(row: dict[str, str]) -> str:
    return row.get("fingerprint", "").replace(":", "").lower()


def _slug(resource: str) -> str:
    return _SLUG_RE.sub("-", resource)


def _scrub(text: str, secrets: tuple[str, ...]) -> str:
    """Remove PEM blocks and every line of the key, certificate and chain from a message."""
    text = _PEM_RE.sub("", text)
    secret_lines = {ln.strip() for pem in secrets for ln in pem.splitlines() if ln.strip()}
    return "\n".join(
        ln for ln in text.splitlines() if ln.strip() not in secret_lines and "PRIVATE" not in ln
    )
