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

    def __init__(self, client: ONTAPAPIClient, config: Config, host: str) -> None:
        """Initialize the service.

        Args:
            client: The pynetappfoundry client, built by :func:`connect_ontap`.
            config: The in-memory config the client was built with.
            host: The cluster address, for messages.
        """
        self._client = client
        self._config = config
        self._host = host

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

    config = InMemoryConfig(
        cluster=params.host,
        username=params.username,
        password=params.password,
        spec_dir=params.spec_file.parent.parent,
        timeout=params.timeout,
        trust=PinnedFingerprintStore(params.fingerprint),
        verify=params.verify_ssl if params.fingerprint is None else None,
        ca_bundle=str(params.ca_bundle) if params.ca_bundle else None,
    )
    extra: dict[str, Any] = {} if session is None else {"session": session}
    client = ONTAPAPIClient(ClusterConfig(name=params.host, ip=params.host), config, **extra)
    return PynetappOntapService(client, config, params.host)
