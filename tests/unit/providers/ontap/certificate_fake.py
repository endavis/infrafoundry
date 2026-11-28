"""A scripted ONTAP cluster for the certificate install tests (documentation values).

One :class:`FakeCluster` holds the certificate tables and the web service binding. Each
:class:`FakeClient` is a view of it with the TLS mode of the real client it stands for: a
client pinned to a SHA-256 fails with a connection error once the cluster serves another
leaf, which is the lock-out the installer is ordered to survive.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from infrafoundry.core.certs.keys import describe
from infrafoundry.providers._netapp.ontap import (
    ConnectionParams,
    OntapAPIError,
    OntapConnectionError,
)

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


def make_cert(common_name: str | None, san: str | None = None) -> tuple[str, str]:
    """Return ``(certificate PEM, key PEM)`` of a throwaway self-signed certificate."""
    key = ec.generate_private_key(ec.SECP256R1())
    attributes = [x509.NameAttribute(NameOID.COMMON_NAME, common_name)] if common_name else []
    name = x509.Name(attributes)
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW)
        .not_valid_after(NOW + dt.timedelta(days=90))
    )
    dns = san or common_name
    if dns:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(dns)]), critical=False
        )
    cert = builder.sign(key, hashes.SHA256())
    return (
        cert.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("ascii"),
    )


class FakeCluster:
    """The certificate tables and web bindings of one cluster, plus a call log."""

    def __init__(self, old_pem: str) -> None:
        self.certs: dict[str, dict[str, Any]] = {}
        self.bindings: dict[str | None, str] = {}
        self.svms = {"svm1": "svm-uuid-1"}
        self.calls: list[tuple[str, str, Any]] = []
        self.bind_error: OntapAPIError | None = None
        self.bind_drops = False
        self.bind_ignored = False
        self.install_error: OntapAPIError | None = None
        self.delete_errors: set[str] = set()
        self.production = False
        self._next = 0
        self.old_uuid = self.add(
            "manual-old", old_pem, svm=None, type="server", key="x-old-key-marker"
        )
        self.bindings[None] = self.old_uuid
        self.svm_old_uuid = self.add("svm-old", old_pem, svm="svm1", type="server", key="x")
        self.bindings["svm-uuid-1"] = self.svm_old_uuid

    def add(
        self, name: str, pem: str, *, svm: str | None, type: str = "server", key: str = ""
    ) -> str:
        """Add a certificate row and return its UUID."""
        self._next += 1
        uuid = f"cert-uuid-{self._next}"
        self.certs[uuid] = {
            "uuid": uuid,
            "name": name,
            "type": type,
            "scope": "svm" if svm else "cluster",
            "svm": {"name": svm} if svm else None,
            "public_certificate": pem,
            "private_key": key,
        }
        return uuid

    def names(self, svm: str | None = None) -> set[str]:
        """Return the names of the certificates in the cluster scope or of ``svm``."""
        return {c["name"] for c in self.certs.values() if _svm_of(c) == svm}

    def serving_sha(self) -> str:
        """SHA-256 of the leaf the cluster management LIF serves."""
        return describe(self.certs[self.bindings[None]]["public_certificate"]).sha256

    def client(self, label: str, *, pin: str | None = None, validating: bool = False) -> FakeClient:
        """Return a client view with the given TLS mode."""
        return FakeClient(self, label, pin, validating)

    def factory(self, params: ConnectionParams) -> FakeClient:
        """Stand-in for ``connect_ontap``: the TLS mode follows the parameters."""
        if params.tls_server_name:
            return self.client("validating", validating=True)
        return self.client(f"pinned:{(params.fingerprint or '')[:8]}", pin=params.fingerprint)


def _svm_of(cert: dict[str, Any]) -> str | None:
    svm = cert.get("svm")
    return svm["name"] if svm else None


class FakeClient:
    """An :class:`OntapCertificateService` over a :class:`FakeCluster`."""

    def __init__(self, cluster: FakeCluster, label: str, pin: str | None, validating: bool) -> None:
        self.cluster = cluster
        self.label = label
        self.pin = pin
        self.validating = validating

    def _enter(self, verb: str, arg: Any = None) -> None:
        self.cluster.calls.append((self.label, verb, arg))
        if self.pin is not None and self.pin != self.cluster.serving_sha():
            raise OntapConnectionError("the TLS certificate does not match the pinned one")
        if self.validating and not self.cluster.production:
            raise OntapConnectionError("validation failed")

    def cluster_info(self) -> dict[str, Any]:
        self._enter("cluster_info")
        return {"name": "cluster1"}

    def find_certificate(self, name: str, svm: str | None) -> dict[str, Any] | None:
        self._enter("find", (name, svm))
        for cert in self.cluster.certs.values():
            if cert["name"] == name and _svm_of(cert) == svm and cert["type"] == "server":
                return dict(cert)
        return None

    def list_server_certificates(self, svm: str | None) -> list[dict[str, Any]]:
        self._enter("list", svm)
        return [
            dict(c)
            for c in self.cluster.certs.values()
            if _svm_of(c) == svm and c["type"] == "server"
        ]

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
        self._enter(
            "install",
            {"name": name, "common_name": common_name, "intermediates": list(intermediates)},
        )
        if self.cluster.install_error:
            raise self.cluster.install_error
        return self.cluster.add(name, public_certificate, svm=svm, key=private_key)

    def delete_certificate(self, uuid: str) -> None:
        self._enter("delete", uuid)
        name = self.cluster.certs[uuid]["name"]
        if name in self.cluster.delete_errors:
            raise OntapAPIError("cannot delete")
        del self.cluster.certs[uuid]

    def svm_uuid(self, svm: str) -> str:
        self._enter("svm_uuid", svm)
        return self.cluster.svms[svm]

    def web_certificate_uuid(self, svm_uuid: str | None) -> str | None:
        self._enter("web_uuid", svm_uuid)
        return self.cluster.bindings.get(svm_uuid)

    def bind_web_certificate(self, certificate_uuid: str, svm_uuid: str | None) -> None:
        self._enter("bind", (certificate_uuid, svm_uuid))
        if self.cluster.bind_error:
            raise self.cluster.bind_error
        if not self.cluster.bind_ignored:
            self.cluster.bindings[svm_uuid] = certificate_uuid
        if self.cluster.bind_drops and svm_uuid is None:
            raise OntapConnectionError("connection dropped")
