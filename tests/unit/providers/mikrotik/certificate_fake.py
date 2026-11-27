"""A scripted RouterOS device for the certificate install tests (documentation values)."""

from __future__ import annotations

import copy
import datetime as dt
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from infrafoundry.core.certs.keys import describe
from infrafoundry.providers.mikrotik.client import RouterOSAPIError, RouterOSConnectionError

NOW = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


def make_cert(common_name: str) -> tuple[str, str]:
    """Return ``(certificate PEM, key PEM)`` of a throwaway self-signed certificate."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW)
        .not_valid_after(NOW + dt.timedelta(days=90))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(common_name)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return (
        cert.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("ascii"),
    )


class FakeRouterOSCerts:
    """In-memory ``file``, ``certificate`` and ``ip/service`` tables with a call log."""

    def __init__(self, *, key_attaches: bool = True) -> None:
        self.tables: dict[str, list[dict[str, str]]] = {
            "file": [],
            "certificate": [],
            "ip/service": [
                {".id": "*A", "name": "api-ssl", "certificate": "old-manual"},
                {".id": "*B", "name": "www-ssl", "certificate": "old-manual"},
                {".id": "*C", "name": "sstp", "certificate": ""},
            ],
        }
        self.calls: list[tuple[Any, ...]] = []
        self.errors: dict[tuple[str, str], RouterOSAPIError | RouterOSConnectionError] = {}
        self.key_attaches = key_attaches
        self._next = 100

    def add_row(self, path: str, **row: str) -> str:
        """Add a row and return its id."""
        self._next += 1
        row_id = f"*{self._next}"
        self.tables[path].append({".id": row_id, **row})
        return row_id

    def _fail(self, verb: str, path: str) -> None:
        error = self.errors.get((verb, path))
        if error is not None:
            raise error

    def get(self, path: str) -> list[dict[str, str]]:
        self.calls.append(("GET", path))
        self._fail("GET", path)
        return copy.deepcopy(self.tables.get(path, []))

    def put(self, path: str, body: dict[str, str]) -> dict[str, str]:
        self.calls.append(("PUT", path, body["name"]))
        self._fail("PUT", path)
        self.add_row(path, name=body["name"], contents=body["contents"])
        return {}

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        name = str((body or {})["file-name"])
        self.calls.append(("POST", path, name))
        self._fail("POST", path)
        contents = next(r["contents"] for r in self.tables["file"] if r["name"] == name)
        if "PRIVATE KEY" in contents:
            if self.key_attaches:
                leaf = name.removesuffix("-key.key") + "-leaf.crt_0"
                for row in self.tables["certificate"]:
                    if row["name"] == leaf:
                        row["private-key"] = "true"
            return {}
        known = {r["fingerprint"] for r in self.tables["certificate"]}
        blocks = contents.split("-----END CERTIFICATE-----")
        for index, block in enumerate(b for b in blocks if "BEGIN CERTIFICATE" in b):
            sha = describe(block + "-----END CERTIFICATE-----\n").sha256
            if sha not in known:
                self.add_row(
                    "certificate",
                    name=f"{name}_{index}",
                    fingerprint=sha,
                    **{"private-key": "false"},
                )
        return {}

    def patch(self, path: str, row_id: str, body: dict[str, str]) -> dict[str, str]:
        self.calls.append(("PATCH", f"{path}/{row_id}", dict(body)))
        self._fail("PATCH", f"{path}/{row_id}")
        row = next(r for r in self.tables[path] if r[".id"] == row_id)
        row.update(body)
        return dict(row)

    def delete(self, path: str, row_id: str) -> None:
        self.calls.append(("DELETE", f"{path}/{row_id}"))
        self._fail("DELETE", f"{path}/{row_id}")
        self.tables[path] = [r for r in self.tables[path] if r[".id"] != row_id]

    def execute(self, script: str) -> str:
        return ""

    def service_cert(self, name: str) -> str:
        """The certificate an ``ip/service`` row points at."""
        return next(r["certificate"] for r in self.tables["ip/service"] if r["name"] == name)

    def cert_names(self) -> list[str]:
        """Names of the certificate rows."""
        return [r["name"] for r in self.tables["certificate"]]
