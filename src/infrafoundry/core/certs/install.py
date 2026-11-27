"""Install targets: parsing, resolving against a provider's resource, and served-cert checks."""

from __future__ import annotations

import re
import shlex
import socket
import ssl
import subprocess  # nosec B404  # runs ssh with list args
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from infrafoundry.core.certs.keys import der_sha256
from infrafoundry.core.certs.models import CertificateInstallError, CertificateSchemaError
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.ssh_host_keys import FIX_HINT, host_key_config, known_hosts_value

SUPPORTED_TARGET_PROVIDERS = ("host", "proxmox", "oci")
TARGET_RESOURCE_TYPES = {"host": "host", "proxmox": "vm", "oci": "instance"}
TARGET_KINDS = {"proxmox": ("vm", "node")}
"""Optional ``target.kind`` values per provider; absent means the provider's default kind."""
NODE_VERIFY_PORT = 8006
VERIFY_WINDOW_SECONDS = 30.0

_PATH_RE = re.compile(r"^/[A-Za-z0-9._/@+:-]+$")
_MODE_RE = re.compile(r"^[0-7]{3,4}$")
_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
_JUMPHOST_RE = re.compile(r"^[A-Za-z0-9._@:-]+$")
_ADDRESS_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_NODE_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_NODE_REJECTED_KEYS = (
    "cert_path",
    "fullchain_path",
    "key_path",
    "owner",
    "group",
    "cert_mode",
    "key_mode",
    "sudo",
    "reload",
)
_JUMP_OPTS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=10"]
_TARGET_KEYS = frozenset(
    {
        "provider",
        "resource",
        "cert_path",
        "fullchain_path",
        "key_path",
        "owner",
        "group",
        "cert_mode",
        "key_mode",
        "sudo",
        "reload",
        "verify",
        "kind",
        "address",
    }
)

Fetch = Callable[[str, int, str], bytes]
"""``(address, port, server_name) -> DER`` of the certificate the endpoint serves."""

JumpFetch = Callable[[str, str, int, str], bytes]
"""``(jumphost, address, port, server_name) -> DER`` fetched from the jump host."""


@dataclass(frozen=True)
class TargetEndpoint:
    """How to reach the target device over SSH."""

    address: str
    port: int = 22
    user: str | None = None
    key_file: str | None = None
    jumphost: str | None = None
    known_hosts: tuple[str, ...] = ()
    host_key_alias: str | None = None


@dataclass(frozen=True)
class CertificateTarget:
    """Where and how a certificate is installed."""

    provider: str
    resource: str
    key_path: str
    cert_path: str | None = None
    fullchain_path: str | None = None
    owner: str = "root"
    group: str = "root"
    cert_mode: str = "0644"
    key_mode: str = "0600"
    sudo: bool = False
    reload: tuple[str, ...] = ()
    verify_port: int | None = None
    verify_server_name: str | None = None
    endpoint: TargetEndpoint | None = None
    kind: str | None = None


def target_problems(raw: Any, names: Iterable[str], where: str) -> list[str]:
    """Return what is wrong with a raw ``target`` mapping (empty when valid). No network.

    Args:
        raw: The ``config.target`` value.
        names: The certificate's names, to decide whether ``server_name`` is required.
        where: Prefix for every message.
    """
    if not isinstance(raw, dict):
        return [f"{where} is required and must be a mapping"]
    problems: list[str] = []
    unknown = sorted(set(raw) - _TARGET_KEYS)
    if unknown:
        problems.append(f"{where} has unknown keys: {', '.join(map(str, unknown))}")
    provider = raw.get("provider")
    if provider not in SUPPORTED_TARGET_PROVIDERS:
        problems.append(f"{where}.provider must be one of: {', '.join(SUPPORTED_TARGET_PROVIDERS)}")
    kind = raw.get("kind")
    if kind is not None and kind not in TARGET_KINDS.get(str(provider), ()):
        allowed = ", ".join(TARGET_KINDS.get(str(provider), ())) or "none for this provider"
        problems.append(f"{where}.kind must be one of: {allowed}")
    if kind == "node" and provider == "proxmox":
        return problems + _node_target_problems(raw, list(names), where)
    if not isinstance(raw.get("resource"), str) or not raw.get("resource"):
        problems.append(f"{where}.resource must name the target resource")
    if not (raw.get("cert_path") or raw.get("fullchain_path")):
        problems.append(f"{where} needs cert_path and/or fullchain_path")
    for key in ("cert_path", "fullchain_path", "key_path"):
        value = raw.get(key)
        if key == "key_path" and value is None:
            problems.append(f"{where}.key_path is required")
        elif value is not None and not (isinstance(value, str) and _PATH_RE.fullmatch(value)):
            problems.append(f"{where}.{key} must be an absolute path of plain characters")
    paths = [raw.get(k) for k in ("cert_path", "fullchain_path", "key_path") if raw.get(k)]
    if len(paths) != len(set(paths)):
        problems.append(f"{where} paths must be distinct")
    for key in ("owner", "group"):
        value = raw.get(key, "root")
        if not (isinstance(value, str) and _ACCOUNT_RE.fullmatch(value)):
            problems.append(f"{where}.{key} must be a plain user or group name")
    for key in ("cert_mode", "key_mode"):
        value = raw.get(key, "0644" if key == "cert_mode" else "0600")
        if not (isinstance(value, str) and _MODE_RE.fullmatch(value)):
            problems.append(f'{where}.{key} must be an octal string such as "0600"')
    if "sudo" in raw and not isinstance(raw["sudo"], bool):
        problems.append(f"{where}.sudo must be true or false")
    reload = raw.get("reload", [])
    if not (
        isinstance(reload, list)
        and all(isinstance(a, str) and a and "\x00" not in a and "\n" not in a for a in reload)
    ):
        problems.append(f"{where}.reload must be a list of arguments (an argv, not a shell string)")
    verify = raw.get("verify")
    if verify is not None:
        problems.extend(_verify_problems(verify, list(names), f"{where}.verify"))
    return problems


def _node_target_problems(raw: dict[str, Any], names: list[str], where: str) -> list[str]:
    """Problems of a Proxmox node target: installed through the API, so no SSH or file keys."""
    problems: list[str] = []
    resource = raw.get("resource")
    if not (isinstance(resource, str) and _NODE_NAME_RE.fullmatch(resource)):
        problems.append(f"{where}.resource must be a Proxmox node name (a single host name label)")
    rejected = sorted(k for k in _NODE_REJECTED_KEYS if k in raw)
    if rejected:
        problems.append(
            f"{where} has keys that do not apply to a Proxmox node: {', '.join(rejected)}"
        )
    address = raw.get("address")
    if address is not None and not (
        isinstance(address, str) and _ADDRESS_RE.fullmatch(address) and not address.startswith("-")
    ):
        problems.append(f"{where}.address must be a host name or IP address")
    verify = raw.get("verify")
    if verify is None:
        if address is None and names and all(n.startswith("*.") for n in names):
            problems.append(
                f"{where}.verify.server_name or {where}.address is required "
                "when every name is a wildcard"
            )
    else:
        problems.extend(
            _verify_problems(verify, names if address is None else ["address"], f"{where}.verify")
        )
    return problems


def _verify_problems(verify: Any, names: list[str], where: str) -> list[str]:
    if not isinstance(verify, dict):
        return [f"{where} must be a mapping"]
    problems: list[str] = []
    unknown = sorted(set(verify) - {"port", "server_name"})
    if unknown:
        problems.append(f"{where} has unknown keys: {', '.join(map(str, unknown))}")
    port = verify.get("port", 443)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        problems.append(f"{where}.port must be a port number")
    server_name = verify.get("server_name")
    if server_name is not None and not (isinstance(server_name, str) and server_name):
        problems.append(f"{where}.server_name must be a host name")
    if server_name is None and all(n.startswith("*.") for n in names):
        problems.append(f"{where}.server_name is required when every name is a wildcard")
    return problems


def parse_target(raw: dict[str, Any], names: Iterable[str]) -> CertificateTarget:
    """Build a target (without an endpoint) from a mapping that passed ``target_problems``.

    Args:
        raw: The ``config.target`` mapping.
        names: The certificate's names, to default the verification server name.

    Raises:
        CertificateSchemaError: If the mapping is invalid.
    """
    name_list = list(names)
    problems = target_problems(raw, name_list, "target")
    if problems:
        raise CertificateSchemaError("; ".join(problems))
    verify = raw.get("verify")
    port: int | None = None
    server_name: str | None = None
    if raw.get("kind") == "node":
        verify_map = verify if isinstance(verify, dict) else {}
        return CertificateTarget(
            provider=str(raw["provider"]),
            resource=str(raw["resource"]),
            key_path="",
            verify_port=int(verify_map.get("port", NODE_VERIFY_PORT)),
            verify_server_name=verify_map.get("server_name")
            or next((n for n in name_list if not n.startswith("*.")), None)
            or raw.get("address"),
            kind="node",
        )
    if isinstance(verify, dict):
        port = int(verify.get("port", 443))
        server_name = verify.get("server_name") or next(
            (n for n in name_list if not n.startswith("*.")), None
        )
    return CertificateTarget(
        provider=str(raw["provider"]),
        resource=str(raw["resource"]),
        key_path=str(raw["key_path"]),
        cert_path=raw.get("cert_path"),
        fullchain_path=raw.get("fullchain_path"),
        owner=str(raw.get("owner", "root")),
        group=str(raw.get("group", "root")),
        cert_mode=str(raw.get("cert_mode", "0644")),
        key_mode=str(raw.get("key_mode", "0600")),
        sudo=raw.get("sudo", False) is True,
        reload=tuple(raw.get("reload", [])),
        verify_port=port,
        verify_server_name=server_name,
    )


def resolve_target(
    raw: dict[str, Any], names: Iterable[str], resources: Iterable[ResourceConfig]
) -> CertificateTarget:
    """Parse a target and attach the SSH endpoint of the resource it names.

    Args:
        raw: The ``config.target`` mapping.
        names: The certificate's names.
        resources: Every resource of the environment.

    Raises:
        CertificateSchemaError: If the target is invalid or names no such resource.
    """
    target = parse_target(raw, names)
    if target.kind == "node":
        address = str(raw.get("address") or target.verify_server_name or "")
        return CertificateTarget(**{**target.__dict__, "endpoint": TargetEndpoint(address=address)})
    resource_type = TARGET_RESOURCE_TYPES[target.provider]
    host = next(
        (
            r
            for r in resources
            if r.provider == target.provider
            and r.type == resource_type
            and r.name == target.resource
        ),
        None,
    )
    if host is None:
        raise CertificateSchemaError(
            f"target {target.provider} resource '{target.resource}' is not declared"
        )
    if resource_type != "host":
        return CertificateTarget(**{**target.__dict__, "endpoint": _pinned_endpoint(host)})
    config = host.config or {}
    endpoint = TargetEndpoint(
        address=str(config.get("address", "")),
        port=int(config.get("ssh_port", 22)),
        user=config.get("ssh_user"),
        key_file=config.get("ssh_private_key_file"),
    )
    if not endpoint.address or endpoint.address.startswith("-"):
        raise CertificateSchemaError(f"target host '{target.resource}' has no usable address")
    return CertificateTarget(**{**target.__dict__, "endpoint": endpoint})


def _pinned_endpoint(resource: ResourceConfig) -> TargetEndpoint:
    """Build a VM's or instance's endpoint from its pinned host key and package variables."""
    name = resource.name
    try:
        spec = host_key_config(resource)
    except ValueError as exc:
        raise CertificateSchemaError(
            f"target '{name}' has an invalid ssh_host_key ({exc}); {FIX_HINT}"
        ) from None
    if spec is None:
        raise CertificateSchemaError(
            f"target '{name}' has no ssh_host_key, so its SSH host key cannot be checked; "
            f"{FIX_HINT}"
        )
    if not _ADDRESS_RE.fullmatch(spec.address) or spec.address.startswith("-"):
        raise CertificateSchemaError(f"target '{name}' has no usable ssh_host_key.address")
    pinned = tuple(line for line in known_hosts_value([resource]).split(";") if line)
    if not pinned:
        raise CertificateSchemaError(
            f"target '{name}' has no pinned SSH host key in its package secrets; {FIX_HINT}"
        )
    variables = resource.package_variables or {}
    jumphost = str(variables.get("jumphost", "") or "").strip()
    if jumphost and (jumphost.startswith("-") or not _JUMPHOST_RE.fullmatch(jumphost)):
        raise CertificateSchemaError(f"target '{name}' has an unusable jumphost")
    user = str(variables.get("ssh_user", "") or "").strip() or (
        jumphost.split("@", 1)[0] if "@" in jumphost else ""
    )
    if not user:
        raise CertificateSchemaError(
            f"target '{name}' needs the package variable ssh_user (or a user@ in jumphost)"
        )
    if user.startswith("-") or not _ACCOUNT_RE.fullmatch(user):
        raise CertificateSchemaError(f"target '{name}' has an unusable ssh_user")
    return TargetEndpoint(
        address=spec.address,
        port=22,
        user=user,
        key_file=None,
        jumphost=jumphost or None,
        known_hosts=pinned,
        host_key_alias=name,
    )


def fetch_served_der_via_jumphost(
    jumphost: str,
    address: str,
    port: int,
    server_name: str,
    run: Callable[..., Any] = subprocess.run,
) -> bytes:
    """Fetch the leaf certificate an endpoint serves, through the jump host (strict ssh).

    Needs ``openssl`` on the jump host.

    Raises:
        OSError: If ssh or openssl fails, or no certificate comes back.
    """
    host = f"[{address}]" if ":" in address else address
    remote = (
        f"openssl s_client -connect {shlex.quote(f'{host}:{port}')} "
        f"-servername {shlex.quote(server_name)} </dev/null 2>/dev/null "
        "| openssl x509 -outform PEM"
    )
    result = run(
        ["ssh", *_JUMP_OPTS, jumphost, remote],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise OSError(f"fetching through the jump host failed (exit {result.returncode})")
    match = re.search(
        r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
        str(result.stdout or ""),
        re.DOTALL,
    )
    if match is None:
        raise OSError("the endpoint presented no certificate")
    return ssl.PEM_cert_to_DER_cert(match.group(0))


def fetch_served_der(address: str, port: int, server_name: str) -> bytes:
    """Fetch the leaf certificate an endpoint serves, without checking the chain.

    The chain is not checked so that staging certificates can be verified too; the caller
    compares the SHA-256 of what was served with what was installed.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with (
        socket.create_connection((address, port), timeout=10) as sock,
        context.wrap_socket(sock, server_hostname=server_name) as tls,
    ):
        der = tls.getpeercert(binary_form=True)
    if not der:
        raise OSError("the endpoint presented no certificate")
    return der


def verify_served(
    target: CertificateTarget,
    expected_sha256: str,
    *,
    fetch: Fetch = fetch_served_der,
    jump_fetch: JumpFetch = fetch_served_der_via_jumphost,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    window: float = VERIFY_WINDOW_SECONDS,
    interval: float = 2.0,
) -> None:
    """Check the target serves the installed certificate, retrying for ``window`` seconds.

    Args:
        target: A resolved target with ``verify`` set.
        expected_sha256: SHA-256 of the leaf certificate's DER.
        fetch: Fetches the served DER; replaced in tests.
        jump_fetch: Fetches the served DER through the jump host (targets with a jumphost).
        sleep: Sleep function.
        monotonic: Clock for the retry window.
        window: Seconds to keep retrying.
        interval: Seconds between attempts.

    Raises:
        CertificateInstallError: If the served certificate never matches.
    """
    if target.endpoint is None or target.verify_port is None or not target.verify_server_name:
        return
    deadline = monotonic() + window
    last = "no attempt was made"
    while True:
        try:
            if target.endpoint.jumphost:
                der = jump_fetch(
                    target.endpoint.jumphost,
                    target.endpoint.address,
                    target.verify_port,
                    target.verify_server_name,
                )
            else:
                der = fetch(target.endpoint.address, target.verify_port, target.verify_server_name)
            served = der_sha256(der)
            if served == expected_sha256:
                return
            last = "it serves a different certificate"
        except (OSError, ssl.SSLError) as exc:
            last = f"the connection failed: {exc.__class__.__name__}"
        if monotonic() >= deadline:
            raise CertificateInstallError(
                f"verification of '{target.resource}' on port {target.verify_port} failed: {last}"
            )
        sleep(interval)
