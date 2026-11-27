"""Install targets: parsing, resolving, and verifying what a device serves."""

from __future__ import annotations

import ssl
import threading
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from infrafoundry.core.certs.install import (
    fetch_served_der,
    parse_target,
    resolve_target,
    verify_served,
)
from infrafoundry.core.certs.keys import der_sha256
from infrafoundry.core.certs.models import CertificateInstallError, CertificateSchemaError

from .fakes import certificate_resource, host_resource

pytestmark = pytest.mark.unit


def raw_target() -> dict[str, Any]:
    return dict(certificate_resource().config["target"])


def test_parse_target_applies_defaults() -> None:
    target = parse_target(raw_target(), ["*.example.com", "example.com"])
    assert (target.owner, target.group, target.cert_mode, target.key_mode) == (
        "root",
        "root",
        "0644",
        "0600",
    )
    assert target.reload == ("systemctl", "reload", "caddy")
    assert target.verify_port == 443
    assert target.verify_server_name == "proxy.example.com"


def test_verify_server_name_defaults_to_the_first_plain_name() -> None:
    raw = raw_target()
    raw["verify"] = {}
    target = parse_target(raw, ["*.example.com", "example.com"])
    assert target.verify_server_name == "example.com"


def test_no_verify_block_means_no_verification() -> None:
    raw = raw_target()
    del raw["verify"]
    assert parse_target(raw, ["a.example.com"]).verify_port is None


def test_parse_target_rejects_invalid_targets() -> None:
    raw = raw_target()
    raw["key_path"] = "../key"
    with pytest.raises(CertificateSchemaError):
        parse_target(raw, ["a.example.com"])


def test_resolve_target_takes_the_endpoint_from_the_host() -> None:
    target = resolve_target(
        raw_target(), ["example.com"], [host_resource(ssh_private_key_file="k")]
    )
    assert target.endpoint is not None
    assert (target.endpoint.address, target.endpoint.port, target.endpoint.user) == (
        "192.0.2.10",
        2222,
        "deploy",
    )
    assert target.endpoint.key_file == "k"


def test_resolve_target_needs_the_host_to_exist() -> None:
    with pytest.raises(CertificateSchemaError, match="not declared"):
        resolve_target(raw_target(), ["example.com"], [host_resource("other")])


def test_resolve_target_refuses_an_address_that_reads_as_an_option() -> None:
    with pytest.raises(CertificateSchemaError, match="usable address"):
        resolve_target(raw_target(), ["example.com"], [host_resource(address="-oProxyCommand=x")])


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def resolved() -> Any:
    return resolve_target(raw_target(), ["example.com"], [host_resource()])


def test_verify_served_passes_when_the_fingerprint_matches() -> None:
    der = b"served-certificate"
    verify_served(resolved(), der_sha256(der), fetch=lambda a, p, s: der)


def test_verify_served_retries_until_the_new_certificate_appears() -> None:
    clock = Clock()
    answers = [b"old", b"old", b"new"]
    seen: list[tuple[str, int, str]] = []

    def fetch(address: str, port: int, name: str) -> bytes:
        seen.append((address, port, name))
        return answers.pop(0)

    verify_served(
        resolved(), der_sha256(b"new"), fetch=fetch, sleep=clock.sleep, monotonic=clock.monotonic
    )
    assert seen[0] == ("192.0.2.10", 443, "proxy.example.com")
    assert len(clock.sleeps) == 2


def test_verify_served_gives_up_after_the_window() -> None:
    clock = Clock()
    with pytest.raises(CertificateInstallError, match="different certificate"):
        verify_served(
            resolved(),
            der_sha256(b"new"),
            fetch=lambda a, p, s: b"old",
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            window=10,
        )
    assert clock.now >= 10


def test_verify_served_reports_a_connection_failure() -> None:
    clock = Clock()

    def refuse(address: str, port: int, name: str) -> bytes:
        raise ConnectionRefusedError

    with pytest.raises(CertificateInstallError, match="ConnectionRefusedError"):
        verify_served(
            resolved(), "x", fetch=refuse, sleep=clock.sleep, monotonic=clock.monotonic, window=4
        )


def test_verify_served_does_nothing_without_a_verify_block() -> None:
    raw = raw_target()
    del raw["verify"]
    target = resolve_target(raw, ["example.com"], [host_resource()])
    verify_served(target, "x", fetch=lambda a, p, s: (_ for _ in ()).throw(AssertionError))


def test_fetch_served_der_reads_a_self_signed_loopback_server(tmp_path: Path) -> None:
    """A real TLS handshake on loopback: the chain is not checked, so a staging cert works."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "loopback.example.com")])
    import datetime as dt

    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(7)
        .not_valid_before(dt.datetime(2020, 1, 1, tzinfo=dt.UTC))
        .not_valid_after(dt.datetime(2040, 1, 1, tzinfo=dt.UTC))
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = tmp_path / "c.pem", tmp_path / "k.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    import socket

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def serve() -> None:
        conn, _ = server.accept()
        try:
            with context.wrap_socket(conn, server_side=True) as tls:
                tls.recv(1)
        except (ssl.SSLError, OSError):
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        der = fetch_served_der("127.0.0.1", port, "loopback.example.com")
    finally:
        server.close()
        thread.join(timeout=5)
    assert der_sha256(der) == der_sha256(cert.public_bytes(serialization.Encoding.DER))
