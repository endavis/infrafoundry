"""ONTAP REST service layer over pynetappfoundry (ADR-0042).

The bottom layer of the provider stack. :func:`connect_ontap` builds an
:class:`OntapService` for one cluster: credentials and the TLS pin are injected in memory
(see ``_adapter``), reads go through pynetappfoundry's ``QuerySet`` and writes through its
``Mutation`` with ``poll=True`` so a job is waited on. Errors map to the exceptions below;
no message carries a credential.

pynetappfoundry is imported inside functions only, so importing this module works on a
core-only install and :func:`connect_ontap` is where a missing extra surfaces.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.tls_server_name import ServerNameAdapter
from infrafoundry.providers._netapp import require_pynetappfoundry

if TYPE_CHECKING:
    from pynetappfoundry.clients.ontap.api import ONTAPAPIClient
    from pynetappfoundry.core.config import Config
    from requests import Session

logger = logging.getLogger(__name__)

SPEC_DOWNLOAD_COMMAND = "nf config download-spec --api ontap"


class OntapError(InfraFoundryError):
    """Base class of the ONTAP service errors. Never carries a credential."""


class OntapAPIError(OntapError):
    """The cluster rejected a request or a job failed."""


class OntapConnectionError(OntapError):
    """The cluster could not be reached, or its certificate did not match the pin."""


class OntapSpecMissingError(OntapError):
    """The ONTAP OpenAPI spec is not where ``api_spec_dir`` points."""


@dataclass(frozen=True)
class ConnectionParams:
    """What :func:`connect_ontap` needs; the settings object of the provider fits it."""

    host: str
    username: str
    password: str
    fingerprint: str | None
    ca_bundle: Path | None
    verify_ssl: bool | None
    timeout: int
    spec_file: Path
    tls_server_name: str | None = None
    """Validate the CA chain and this host name instead of the pin (an installed production
    certificate, #1684); overrides ``fingerprint``, ``ca_bundle`` and ``verify_ssl``."""


class OntapService(Protocol):
    """What the provider's manager needs from the cluster."""

    def list_interfaces(self, svms: Sequence[str]) -> list[dict[str, Any]]:
        """Return the IP interfaces of the SVMs as nested REST records."""
        ...

    def create_interface(self, **fields: Any) -> None:
        """Create an IP interface from flat dotted field names (one POST)."""
        ...

    def update_interface(self, uuid: str, **fields: Any) -> None:
        """Change an IP interface (one PATCH)."""
        ...

    def delete_interface(self, uuid: str) -> None:
        """Delete an IP interface."""
        ...

    def cluster_info(self) -> dict[str, Any]:
        """Return the cluster ``name`` and ``version`` record."""
        ...

    def list_names(self, kind: str) -> set[str]:
        """Return the names of the cluster's ``svms``, ``nodes`` or ``ports`` (node:port)."""
        ...


class OntapCertificateService(Protocol):
    """What the certificate installer needs from the cluster (#1684)."""

    def cluster_info(self) -> dict[str, Any]:
        """Return the cluster ``name`` and ``version`` record."""
        ...

    def find_certificate(self, name: str, svm: str | None) -> dict[str, Any] | None:
        """Return the server certificate called ``name`` (``uuid``, ``name``,
        ``public_certificate``) in the cluster scope or in ``svm``, else ``None``."""
        ...

    def list_server_certificates(self, svm: str | None) -> list[dict[str, Any]]:
        """Return the ``type: server`` certificates of the cluster scope or of ``svm``."""
        ...

    def install_certificate(
        self,
        *,
        name: str,
        common_name: str,
        public_certificate: str,
        private_key: str,
        intermediates: Sequence[str],
        svm: str | None,
    ) -> str:
        """Install a server certificate and return its UUID."""
        ...

    def delete_certificate(self, uuid: str) -> None:
        """Delete an installed certificate."""
        ...

    def svm_uuid(self, svm: str) -> str:
        """Return the UUID of the SVM called ``svm``."""
        ...

    def web_certificate_uuid(self, svm_uuid: str | None) -> str | None:
        """Return the UUID of the certificate the cluster (or SVM) web service uses."""
        ...

    def bind_web_certificate(self, certificate_uuid: str, svm_uuid: str | None) -> None:
        """Make the cluster (or SVM) web service use the certificate.

        The cluster web service restarts, which can drop the connection: that surfaces as
        :class:`OntapConnectionError`. An SVM binding waits for its job.
        """
        ...


def spec_hint(spec_file: Path) -> str:
    """Return the message that names the missing spec and where to download it (built offline)."""
    from pynetappfoundry import __version__
    from pynetappfoundry.core.config_checks import SPEC_FILES
    from pynetappfoundry.core.spec_source import installed_repository, resolve_ref, spec_url

    where = f"the ONTAP OpenAPI spec is missing at {spec_file}"
    try:
        source = next(src for _, api, _, src in SPEC_FILES if api == "ontap")
        owner, repo = installed_repository()
        url = spec_url(owner, repo, resolve_ref(__version__).ref, source)
    except Exception as exc:  # an offline hint must never hide the real problem
        logger.debug("could not build the spec download URL: %s", type(exc).__name__)
        return f"{where}; fetch it with `{SPEC_DOWNLOAD_COMMAND}` and put it there"
    return f"{where}; download {url} to that path"


class PynetappOntapService:
    """An :class:`OntapService` backed by a real ``ONTAPAPIClient``."""

    def __init__(
        self, client: ONTAPAPIClient, config: Config, host: str, *, validated: bool = False
    ) -> None:
        """Initialize the service.

        Args:
            client: The pynetappfoundry client, built by :func:`connect_ontap`.
            config: The in-memory config the client was built with.
            host: The cluster address, for messages.
            validated: True when the client validates the CA chain and host name (an installed
                production certificate), which changes the TLS failure message.
        """
        self._client = client
        self._config = config
        self._host = host
        self._validated = validated

    def _translate(self, exc: Exception) -> OntapError:
        """Map a library or HTTP exception to a service error without credentials."""
        import requests
        from pynetappfoundry.clients.trust import HostIdentityChangedError
        from pynetappfoundry.query.job import JobError

        if isinstance(exc, HostIdentityChangedError):
            return OntapConnectionError(
                f"the TLS certificate presented by '{self._host}' does not match the pinned "
                "tls_fingerprint; if the certificate was replaced on purpose, re-pin "
                "tls_fingerprint (openssl x509 -noout -fingerprint -sha256)"
            )
        if isinstance(exc, requests.HTTPError):
            return OntapAPIError(_http_message(exc))
        if isinstance(exc, requests.exceptions.SSLError) and self._validated:
            return OntapConnectionError(
                f"The certificate '{self._host}' presented failed validation (CA chain or host "
                "name). If the installed certificate is wrong or expired, select a working "
                "server certificate for the web service on the cluster console (the "
                "'security ssl' commands), then run 'foundry certs issue' again."
            )
        if isinstance(exc, requests.exceptions.SSLError):
            return OntapConnectionError(
                f"TLS verification of '{self._host}' failed: check tls_fingerprint, ca_bundle "
                "and verify_ssl"
            )
        if isinstance(exc, requests.RequestException):
            return OntapConnectionError(f"cannot reach '{self._host}': {type(exc).__name__}")
        if isinstance(exc, JobError):
            return OntapAPIError(f"ONTAP job failed: {exc.message} (code {exc.error_code})")
        if isinstance(exc, TimeoutError):
            return OntapAPIError(str(exc))
        return OntapError(f"{type(exc).__name__}: {exc}")

    def list_interfaces(self, svms: Sequence[str]) -> list[dict[str, Any]]:
        """Return the IP interfaces of the SVMs as nested REST records."""
        from pynetappfoundry.models.ontap.network.ip.interfaces.model import OntapIpInterface
        from pynetappfoundry.query.queryset import QuerySet

        rows: list[dict[str, Any]] = []
        for svm in svms:
            try:
                query = QuerySet(OntapIpInterface, self._client, config=self._config)
                rows.extend(m.model_dump() for m in query.filter(**{"svm.name": svm}).all())
            except Exception as exc:
                raise self._translate(exc) from None
        return rows

    def create_interface(self, **fields: Any) -> None:
        """Create an IP interface from flat dotted field names (one POST)."""
        from pynetappfoundry.models.ontap.network.ip.interfaces.model import OntapIpInterface
        from pynetappfoundry.query.mutation import Mutation

        try:
            Mutation(OntapIpInterface, self._client).create(poll=True, **fields)
        except Exception as exc:
            raise self._translate(exc) from None

    def update_interface(self, uuid: str, **fields: Any) -> None:
        """Change an IP interface (one PATCH)."""
        from pynetappfoundry.models.ontap.network.ip.interfaces.model import OntapIpInterface
        from pynetappfoundry.query.mutation import Mutation

        try:
            Mutation(OntapIpInterface, self._client).update(uuid, poll=True, **fields)
        except Exception as exc:
            raise self._translate(exc) from None

    def delete_interface(self, uuid: str) -> None:
        """Delete an IP interface, waiting for the job when the cluster starts one."""
        from pynetappfoundry.models.ontap.network.ip.interfaces.model import OntapIpInterface
        from pynetappfoundry.query.job import JobTracker
        from pynetappfoundry.query.mutation import Mutation

        try:
            response = Mutation(OntapIpInterface, self._client).delete(uuid)
            if isinstance(response, dict) and "job" in response:
                JobTracker.from_response(response, self._client).wait()
        except Exception as exc:
            raise self._translate(exc) from None

    def cluster_info(self) -> dict[str, Any]:
        """Return the cluster ``name`` and ``version`` record."""
        try:
            response = self._client.call_endpoint(
                "/cluster", query_params={"fields": "name,version"}
            )
        except Exception as exc:
            raise self._translate(exc) from None
        return response if isinstance(response, dict) else {}

    def list_names(self, kind: str) -> set[str]:
        """Return the names of the cluster's ``svms``, ``nodes`` or ``ports`` (node:port)."""
        endpoints = {
            "svms": ("/svm/svms", "name"),
            "nodes": ("/cluster/nodes", "name"),
            "ports": ("/network/ethernet/ports", "name,node.name"),
        }
        path, fields = endpoints[kind]
        try:
            response = self._client.get_all_records(path, query_params={"fields": fields})
        except Exception as exc:
            raise self._translate(exc) from None
        names: set[str] = set()
        for record in response.get("records", []):
            name = str(record.get("name", ""))
            if kind == "ports":
                name = f"{(record.get('node') or {}).get('name', '')}:{name}"
            names.add(name)
        return names

    # -- certificates (#1684) -------------------------------------------------------------

    _CERT_FIELDS = "uuid,name,type,scope,svm.name,common_name,public_certificate"

    def _certificates(self, **filters: str) -> list[dict[str, Any]]:
        query = {"fields": self._CERT_FIELDS, "type": "server", **filters}
        try:
            response = self._client.get_all_records("/security/certificates", query_params=query)
        except Exception as exc:
            raise self._translate(exc) from None
        return [r for r in response.get("records", []) if isinstance(r, dict)]

    @staticmethod
    def _scope_filter(svm: str | None) -> dict[str, str]:
        return {"svm.name": svm} if svm else {"scope": "cluster"}

    def find_certificate(self, name: str, svm: str | None) -> dict[str, Any] | None:
        """Return the server certificate called ``name`` in the cluster scope or ``svm``."""
        rows = self._certificates(name=name, **self._scope_filter(svm))
        return rows[0] if rows else None

    def list_server_certificates(self, svm: str | None) -> list[dict[str, Any]]:
        """Return the ``type: server`` certificates of the cluster scope or of ``svm``."""
        return self._certificates(**self._scope_filter(svm))

    def install_certificate(
        self,
        *,
        name: str,
        common_name: str,
        public_certificate: str,
        private_key: str,
        intermediates: Sequence[str],
        svm: str | None,
    ) -> str:
        """Install a server certificate with its key and chain and return its UUID.

        Request bodies are never logged, so the private key stays out of the logs.
        """
        body: dict[str, Any] = {
            "type": "server",
            "name": name,
            "common_name": common_name,
            "public_certificate": public_certificate,
            "private_key": private_key,
        }
        if intermediates:
            body["intermediate_certificates"] = list(intermediates)
        if svm:
            body["svm"] = {"name": svm}
        try:
            response = self._client.call_endpoint(
                "/security/certificates",
                method="POST",
                query_params={"return_records": "true"},
                body=body,
            )
            self._wait_if_job(response)
        except Exception as exc:
            raise self._translate(exc) from None
        records = response.get("records") if isinstance(response, dict) else None
        if records and isinstance(records[0], dict) and records[0].get("uuid"):
            return str(records[0]["uuid"])
        found = self.find_certificate(name, svm)
        if found is None or not found.get("uuid"):
            raise OntapAPIError("ONTAP accepted the certificate but did not return it")
        return str(found["uuid"])

    def delete_certificate(self, uuid: str) -> None:
        """Delete an installed certificate."""
        try:
            response = self._client.call_endpoint(
                "/security/certificates/{uuid}", method="DELETE", path_params={"uuid": uuid}
            )
            self._wait_if_job(response)
        except Exception as exc:
            raise self._translate(exc) from None

    def svm_uuid(self, svm: str) -> str:
        """Return the UUID of the SVM called ``svm``."""
        try:
            response = self._client.get_all_records(
                "/svm/svms", query_params={"name": svm, "fields": "uuid,name"}
            )
        except Exception as exc:
            raise self._translate(exc) from None
        for record in response.get("records", []):
            if record.get("name") == svm and record.get("uuid"):
                return str(record["uuid"])
        raise OntapAPIError(f"the cluster has no SVM '{svm}'")

    def _web_path(self, svm_uuid: str | None) -> tuple[str, dict[str, Any] | None]:
        if svm_uuid:
            return "/svm/svms/{svm.uuid}/web", {"svm.uuid": svm_uuid}
        return "/cluster/web", None

    def web_certificate_uuid(self, svm_uuid: str | None) -> str | None:
        """Return the UUID of the certificate the cluster (or SVM) web service uses."""
        path, params = self._web_path(svm_uuid)
        try:
            response = self._client.call_endpoint(
                path, path_params=params, query_params={"fields": "certificate.uuid"}
            )
        except Exception as exc:
            raise self._translate(exc) from None
        certificate = response.get("certificate") if isinstance(response, dict) else None
        uuid = certificate.get("uuid") if isinstance(certificate, dict) else None
        return str(uuid) if uuid else None

    def bind_web_certificate(self, certificate_uuid: str, svm_uuid: str | None) -> None:
        """Make the cluster (or SVM) web service use the certificate.

        The cluster call is neither retried nor polled: the web service restarts on the new
        certificate and the pinned session breaks. An SVM binding waits for its job.
        """
        from pynetappfoundry.core.models import RetryConfig

        path, params = self._web_path(svm_uuid)
        try:
            response = self._client.call_endpoint(
                path,
                method="PATCH",
                path_params=params,
                body={"certificate": {"uuid": certificate_uuid}},
                retry_config=RetryConfig(enabled=False),
            )
            if svm_uuid:
                self._wait_if_job(response)
        except Exception as exc:
            raise self._translate(exc) from None

    def _wait_if_job(self, response: Any) -> None:
        if isinstance(response, dict) and "job" in response:
            from pynetappfoundry.query.job import JobTracker

            JobTracker.from_response(response, self._client).wait()


def _http_message(exc: Exception) -> str:
    """Return ONTAP's error message of a failed request, else the status line."""
    response = getattr(exc, "response", None)
    try:
        error = response.json().get("error", {}) if response is not None else {}
    except ValueError:
        error = {}
    message = error.get("message")
    code = error.get("code")
    if message:
        return f"ONTAP rejected the request: {message}" + (f" (code {code})" if code else "")
    status = getattr(response, "status_code", None)
    return f"ONTAP rejected the request (HTTP {status})" if status else "ONTAP rejected the request"


def connect_ontap(params: ConnectionParams, *, session: Session | None = None) -> OntapService:
    """Build the service for one cluster, with credentials and the TLS pin held in memory.

    Args:
        params: Host, credentials, trust settings and the spec path.
        session: A ``requests`` session to use; replaced in tests.

    Raises:
        NetAppDependencyError: If pynetappfoundry is not installed.
        OntapSpecMissingError: If the OpenAPI spec is not at ``params.spec_file``.
    """
    require_pynetappfoundry()
    if not params.spec_file.is_file():
        raise OntapSpecMissingError(spec_hint(params.spec_file))

    from pynetappfoundry.clients.ontap.api import ONTAPAPIClient
    from pynetappfoundry.core.models import ClusterConfig

    from ._adapter import InMemoryConfig, PinnedFingerprintStore

    validated = params.tls_server_name is not None
    config = InMemoryConfig(
        cluster=params.host,
        username=params.username,
        password=params.password,
        spec_dir=params.spec_file.parent.parent,
        timeout=params.timeout,
        trust=PinnedFingerprintStore(None if validated else params.fingerprint),
        verify=True if validated else (params.verify_ssl if params.fingerprint is None else None),
        ca_bundle=None if validated else (str(params.ca_bundle) if params.ca_bundle else None),
    )
    extra: dict[str, Any] = {} if session is None else {"session": session}
    client = ONTAPAPIClient(ClusterConfig(name=params.host, ip=params.host), config, **extra)
    if params.tls_server_name:
        # The pinning adapter pins nothing when ``verify`` is not False; this one adds SNI
        # and the host name check for the certificate's DNS name (the longest prefix wins).
        client.session.mount(client.base_url, ServerNameAdapter(params.tls_server_name))
    return PynetappOntapService(client, config, params.host, validated=validated)
