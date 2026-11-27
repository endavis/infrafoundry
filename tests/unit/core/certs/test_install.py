"""Install targets: parsing, resolving, and verifying what a device serves."""

from __future__ import annotations

import socket
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
    CertificateTarget,
    fetch_served_der,
    fetch_served_der_via_jumphost,
    parse_target,
    resolve_target,
    target_problems,
    verify_served,
)
from infrafoundry.core.certs.keys import der_sha256
from infrafoundry.core.certs.models import CertificateInstallError, CertificateSchemaError
from infrafoundry.core.provider import ResourceConfig

from .fakes import (
    PUBLIC,
    FakeRun,
    TestCa,
    certificate_resource,
    host_resource,
    vm_resource,
    vm_target,
)

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


def test_fetch_served_der_refuses_tls_older_than_1_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """The verify probe never negotiates TLS 1.0 or 1.1."""
    built: list[ssl.SSLContext] = []

    def wrap_socket(self: ssl.SSLContext, *args: Any, **kwargs: Any) -> Any:
        built.append(self)
        raise OSError("stop before the handshake")

    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap_socket)
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        with pytest.raises(OSError, match="stop before"):
            fetch_served_der("127.0.0.1", server.getsockname()[1], "loopback.example.com")
    finally:
        server.close()
    assert built[0].minimum_version == ssl.TLSVersion.TLSv1_2


# --- VM and instance targets (#1682, PR 3) ---------------------------------------------------


def _vm(**over: object) -> ResourceConfig:
    return vm_resource(**over)  # type: ignore[arg-type]


def _resolve(resource: ResourceConfig) -> CertificateTarget:
    return resolve_target(vm_target(resource), ["example.com"], [resource])


def test_a_proxmox_vm_resolves_to_a_pinned_jump_endpoint() -> None:
    endpoint = _resolve(_vm()).endpoint
    assert endpoint is not None
    assert (endpoint.address, endpoint.port, endpoint.user) == ("192.0.2.20", 22, "deploy")
    assert endpoint.jumphost == "jump.example.com"
    assert endpoint.key_file is None
    assert endpoint.host_key_alias == "app-01"
    assert endpoint.known_hosts == (f"app-01,192.0.2.20 {PUBLIC}",)


def test_an_oci_instance_without_a_jumphost_is_direct() -> None:
    endpoint = _resolve(_vm(provider="oci", rtype="instance", jumphost=None)).endpoint
    assert endpoint is not None
    assert endpoint.jumphost is None
    assert endpoint.known_hosts


def test_the_user_falls_back_to_the_jumphost_user() -> None:
    endpoint = _resolve(_vm(ssh_user=None, jumphost="ops@jump.example.com")).endpoint
    assert endpoint is not None
    assert endpoint.user == "ops"


def test_no_user_at_all_names_ssh_user() -> None:
    with pytest.raises(CertificateSchemaError, match="ssh_user"):
        _resolve(_vm(ssh_user=None))


@pytest.mark.parametrize(
    "resource",
    [_vm(pinned_block=False), _vm(public=None)],
    ids=["no-ssh-host-key", "no-pinned-public-key"],
)
def test_a_vm_without_a_pin_fails_closed(resource: ResourceConfig) -> None:
    with pytest.raises(CertificateSchemaError, match="foundry secrets host-keys"):
        _resolve(resource)


def test_an_invalid_ssh_host_key_block_fails_closed() -> None:
    resource = _vm(address="bad address")
    with pytest.raises(CertificateSchemaError, match="foundry secrets host-keys"):
        _resolve(resource)


@pytest.mark.parametrize("jumphost", ["-oProxyCommand=x", "jump.example.com;id", "a b"])
def test_an_unsafe_jumphost_is_rejected(jumphost: str) -> None:
    with pytest.raises(CertificateSchemaError, match="jumphost"):
        _resolve(_vm(jumphost=jumphost))


def test_an_unsafe_ssh_user_is_rejected() -> None:
    with pytest.raises(CertificateSchemaError, match="ssh_user"):
        _resolve(_vm(ssh_user="-oX"))


def test_an_undeclared_or_misprovided_vm_is_not_declared() -> None:
    resource = _vm()
    target = vm_target(resource)
    with pytest.raises(CertificateSchemaError, match="not declared"):
        resolve_target(target, ["example.com"], [])
    with pytest.raises(CertificateSchemaError, match="not declared"):
        resolve_target(target, ["example.com"], [_vm(provider="oci")])
    with pytest.raises(CertificateSchemaError, match="not declared"):
        resolve_target(target, ["example.com"], [_vm(rtype="container")])


def test_target_problems_accepts_proxmox_and_oci_only() -> None:
    base = dict(certificate_resource().config["target"])
    for provider in ("host", "proxmox", "oci"):
        assert target_problems({**base, "provider": provider}, ["example.com"], "t") == []
    assert target_problems({**base, "provider": "nope"}, ["example.com"], "t")


def _pem_der() -> tuple[str, bytes]:
    ca = TestCa()
    pem = ca.cert.public_bytes(serialization.Encoding.PEM).decode()
    return pem, ca.cert.public_bytes(serialization.Encoding.DER)


def test_fetch_through_the_jumphost_parses_pem() -> None:
    pem, der = _pem_der()
    run = FakeRun(stdout="noise\n" + pem)
    assert (
        fetch_served_der_via_jumphost("jump.example.com", "2001:db8::1", 443, "a.example.com", run)
        == der
    )
    argv = run.calls[0][0]
    assert argv[:7] == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
    ]
    assert argv[7] == "jump.example.com"
    assert "'[2001:db8::1]:443'" in argv[8] or "[2001:db8::1]:443" in argv[8]
    assert "-servername a.example.com" in argv[8]


def test_fetch_through_the_jumphost_quotes_its_inputs() -> None:
    run = FakeRun(stdout="")
    with pytest.raises(OSError):
        fetch_served_der_via_jumphost("j", "192.0.2.1", 443, "a; id", run)
    assert "'a; id'" in run.calls[0][0][-1]


def test_fetch_through_the_jumphost_fails_on_exit_or_empty_output() -> None:
    with pytest.raises(OSError):
        fetch_served_der_via_jumphost("j", "192.0.2.1", 443, "a", FakeRun(returncode=255))
    with pytest.raises(OSError, match="no certificate"):
        fetch_served_der_via_jumphost("j", "192.0.2.1", 443, "a", FakeRun(stdout=""))


def test_verify_uses_the_jump_fetch_only_with_a_jumphost() -> None:
    der = b"served"
    sha = der_sha256(der)
    calls: list[str] = []

    def direct(address: str, port: int, name: str) -> bytes:
        calls.append("direct")
        return der

    def jump(jumphost: str, address: str, port: int, name: str) -> bytes:
        calls.append(f"jump:{jumphost}")
        return der

    resource = _vm()
    target = resolve_target(
        {**vm_target(resource), "verify": {"port": 443, "server_name": "a.example.com"}},
        ["a.example.com"],
        [resource],
    )
    verify_served(target, sha, fetch=direct, jump_fetch=jump)
    assert calls == ["jump:jump.example.com"]
    direct_resource = _vm(jumphost=None)
    target = resolve_target(
        {**vm_target(direct_resource), "verify": {"port": 443, "server_name": "a.example.com"}},
        ["a.example.com"],
        [direct_resource],
    )
    verify_served(target, sha, fetch=direct, jump_fetch=jump)
    assert calls[-1] == "direct"


# -- Proxmox node targets (#1705) ----------------------------------------------------------


def node_target(**over: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {"provider": "proxmox", "kind": "node", "resource": "node1"}
    raw.update(over)
    return raw


def test_a_node_target_defaults_to_port_8006_and_the_first_plain_name() -> None:
    target = parse_target(node_target(), ["*.example.com", "node1.example.com"])
    assert target.kind == "node"
    assert target.verify_port == 8006
    assert target.verify_server_name == "node1.example.com"


def test_a_node_target_takes_an_explicit_verify_block() -> None:
    raw = node_target(verify={"port": 8443, "server_name": "pve.example.net"})
    target = parse_target(raw, ["node1.example.com"])
    assert (target.verify_port, target.verify_server_name) == (8443, "pve.example.net")


def test_a_node_needs_no_declared_resource_and_verifies_the_address() -> None:
    raw = node_target(address="node1.example.com")
    target = resolve_target(raw, ["*.example.com"], [])
    assert target.endpoint is not None
    assert target.endpoint.address == "node1.example.com"
    assert target.endpoint.jumphost is None
    assert target.verify_server_name == "node1.example.com"


def test_a_node_without_address_verifies_the_server_name() -> None:
    target = resolve_target(node_target(), ["node1.example.com"], [])
    assert target.endpoint is not None
    assert target.endpoint.address == "node1.example.com"


@pytest.mark.parametrize(
    "extra",
    [
        {"key_path": "/etc/pve/key.pem"},
        {"cert_path": "/etc/pve/cert.pem"},
        {"fullchain_path": "/etc/pve/chain.pem"},
        {"reload": ["true"]},
        {"sudo": True},
        {"owner": "root"},
        {"cert_mode": "0644"},
    ],
)
def test_a_node_rejects_ssh_and_file_keys(extra: dict[str, Any]) -> None:
    problems = target_problems(node_target(**extra), ["node1.example.com"], "target")
    assert any("do not apply to a Proxmox node" in p for p in problems)


@pytest.mark.parametrize("name", ["node1.example.com", "-pve", "pve 1", "", "a;b"])
def test_a_node_name_must_be_one_host_label(name: str) -> None:
    problems = target_problems(node_target(resource=name), ["node1.example.com"], "target")
    assert any("node name" in p for p in problems)


@pytest.mark.parametrize("address", ["-oProxyCommand=x", "a b", "pve;1", 5])
def test_a_node_address_must_be_safe(address: Any) -> None:
    problems = target_problems(node_target(address=address), ["node1.example.com"], "target")
    assert any("address" in p for p in problems)


def test_a_wildcard_only_node_needs_a_server_name_or_address() -> None:
    assert any("wildcard" in p for p in target_problems(node_target(), ["*.example.com"], "target"))
    assert not target_problems(
        node_target(address="node1.example.com"), ["*.example.com"], "target"
    )
    raw = node_target(verify={"server_name": "node1.example.com"})
    assert not target_problems(raw, ["*.example.com"], "target")


def test_an_unknown_kind_is_rejected() -> None:
    raw = node_target(kind="cluster")
    assert any("kind must be one of: vm, node" in p for p in target_problems(raw, ["a"], "t"))


@pytest.mark.parametrize("provider", ["host", "oci"])
def test_kind_is_an_error_on_other_providers(provider: str) -> None:
    raw = dict(raw_target(), provider=provider, kind="node")
    assert any("kind must be one of" in p for p in target_problems(raw, ["a.example.com"], "t"))


def test_kind_vm_equals_no_kind() -> None:
    resource = vm_resource(provider="proxmox", rtype="vm")
    plain = resolve_target(vm_target(resource), ["example.com"], [resource])
    explicit = resolve_target({**vm_target(resource), "kind": "vm"}, ["example.com"], [resource])
    assert explicit == plain
    assert plain.kind is None


def test_a_vm_still_needs_its_declared_resource() -> None:
    resource = vm_resource(provider="proxmox", rtype="vm")
    with pytest.raises(CertificateSchemaError, match="not declared"):
        resolve_target(vm_target(resource), ["example.com"], [])


def test_verify_served_fetches_a_node_on_port_8006() -> None:
    target = resolve_target(node_target(), ["node1.example.com"], [])
    der = b"node-certificate"
    seen: list[tuple[str, int, str]] = []

    def fetch(address: str, port: int, server_name: str) -> bytes:
        seen.append((address, port, server_name))
        return der

    verify_served(target, der_sha256(der), fetch=fetch)
    assert seen == [("node1.example.com", 8006, "node1.example.com")]


def mikrotik_target(**over: Any) -> dict[str, Any]:
    return {"provider": "mikrotik", "resource": "edge-services", **over}


def mikrotik_resource(name: str = "edge-services") -> ResourceConfig:
    return ResourceConfig(
        name=name, type="ip.service", provider="mikrotik", config={"name": "www-ssl"}
    )


def test_a_mikrotik_target_needs_no_paths() -> None:
    assert target_problems(mikrotik_target(), ["router.example.com"], "t") == []
    assert (
        target_problems(mikrotik_target(verify={"port": 8443}), ["router.example.com"], "t") == []
    )


def test_a_mikrotik_target_rejects_ssh_keys_and_unknown_ones() -> None:
    problems = target_problems(
        mikrotik_target(key_path="/etc/key", reload=["x"], bogus=1), ["router.example.com"], "t"
    )
    assert any("unknown keys" in p and "key_path" in p for p in problems)


def test_a_mikrotik_target_with_only_wildcards_needs_a_server_name() -> None:
    assert target_problems(mikrotik_target(), ["*.example.com"], "t")
    assert not target_problems(
        mikrotik_target(verify={"server_name": "router.example.com"}), ["*.example.com"], "t"
    )


def test_a_mikrotik_target_always_has_a_server_name_and_no_forced_port() -> None:
    target = parse_target(mikrotik_target(), ["*.example.com", "router.example.com"])
    assert (target.verify_server_name, target.verify_port, target.key_path) == (
        "router.example.com",
        None,
        "",
    )
    assert (
        parse_target(mikrotik_target(verify={"port": 8443}), ["a.example.com"]).verify_port == 8443
    )


def test_a_mikrotik_target_resolves_without_an_endpoint() -> None:
    target = resolve_target(mikrotik_target(), ["router.example.com"], [mikrotik_resource()])
    assert target.endpoint is None
    assert target.env is None


def test_a_mikrotik_target_needs_its_ip_service_resource() -> None:
    with pytest.raises(CertificateSchemaError, match="not declared"):
        resolve_target(mikrotik_target(), ["router.example.com"], [mikrotik_resource("other")])
