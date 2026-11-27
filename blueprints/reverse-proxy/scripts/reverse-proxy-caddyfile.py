#!/usr/bin/env python3
"""Render the reverse-proxy Caddyfile from the blueprint's routes.

Standard library only. Reads RP_ROUTES, RP_ALLOWED (both JSON), RP_DOMAIN and RP_CERT_DIR
from the environment and prints the Caddyfile on stdout. Every value that reaches the
Caddyfile is validated first; a bad one raises ValueError naming the route, and the
command exits non-zero with the message on stderr. Automatic HTTPS is off: the
certificate comes from the acme provider and is installed on the VM.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import sys
from typing import Any
from urllib.parse import urlsplit

LABEL_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")
CERT_DIR_RE = re.compile(r"^/[A-Za-z0-9._/-]*$")
HOST_HEADER_RE = re.compile(r"^[A-Za-z0-9.:-]*$")
BACKEND_FORBIDDEN_RE = re.compile(r"[\s{}#\"'`\\$;|&<>]")
UPSTREAM = "upstream"


class Route:
    """One validated route."""

    def __init__(
        self,
        name: str,
        backend: str,
        insecure: bool,
        host_header: str,
        allow_from: list[str],
    ) -> None:
        self.name = name
        self.backend = backend
        self.insecure = insecure
        self.host_header = host_header
        self.allow_from = allow_from


def _load_list(raw: str, what: str) -> list[Any]:
    try:
        value = json.loads(raw) if raw.strip() else []
    except ValueError as exc:
        raise ValueError(f"{what} is not valid JSON: {exc}") from exc
    if not isinstance(value, list):
        raise ValueError(f"{what} must be a list")
    return value


def _cidrs(raw: Any, where: str) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError(f"{where} must be a list of CIDRs")
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError(f"{where} holds a non-string entry {item!r}")
        try:
            out.append(str(ipaddress.ip_network(item, strict=False)))
        except ValueError as exc:
            raise ValueError(f"{where} entry {item!r} is not a CIDR") from exc
    return out


def _check_backend(name: str, backend: Any) -> str:
    if not isinstance(backend, str) or not backend:
        raise ValueError(f"route '{name}': backend must be a non-empty string")
    if BACKEND_FORBIDDEN_RE.search(backend):
        raise ValueError(f"route '{name}': backend '{backend}' holds a forbidden character")
    parts = urlsplit(backend)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"route '{name}': backend must be http(s)://host[:port], got '{backend}'")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError(f"route '{name}': backend must not carry a path or query")
    return backend.rstrip("/")


def parse_routes(raw_json: str, allowed_json: str) -> list[Route]:
    """Validate the routes and apply the allowed_networks fallback.

    Args:
        raw_json: JSON list of route mappings.
        allowed_json: JSON list of CIDRs used by routes without their own allow_from.

    Returns:
        The routes sorted by name.

    Raises:
        ValueError: A value is invalid; the message names the route.
    """
    allowed = _cidrs(_load_list(allowed_json, "allowed_networks"), "allowed_networks")
    routes: list[Route] = []
    seen: set[str] = set()
    for index, entry in enumerate(_load_list(raw_json, "routes")):
        if not isinstance(entry, dict):
            raise ValueError(f"routes[{index}] must be a mapping")
        name = entry.get("name")
        if not isinstance(name, str) or not LABEL_RE.match(name):
            raise ValueError(f"routes[{index}]: name {name!r} is not a DNS label")
        if name in seen:
            raise ValueError(f"route '{name}': name is not unique")
        seen.add(name)
        backend = _check_backend(name, entry.get("backend"))
        insecure = entry.get("insecure", False)
        if not isinstance(insecure, bool):
            raise ValueError(f"route '{name}': insecure must be true or false")
        if insecure and not backend.startswith("https://"):
            raise ValueError(f"route '{name}': insecure only applies to an https backend")
        host_header = entry.get("host_header", "")
        if not isinstance(host_header, str) or not HOST_HEADER_RE.match(host_header):
            raise ValueError(f"route '{name}': host_header '{host_header}' is not valid")
        own = _cidrs(entry.get("allow_from", []), f"route '{name}': allow_from")
        routes.append(Route(name, backend, insecure, host_header, own or allowed))
    return sorted(routes, key=lambda r: r.name)


def render_caddyfile(routes: list[Route], domain: str, cert_dir: str) -> str:
    """Render the Caddyfile for the routes.

    Args:
        routes: Validated routes from :func:`parse_routes`.
        domain: The domain the routes are served under.
        cert_dir: Absolute directory holding proxy.fullchain.pem and proxy.key.

    Returns:
        The Caddyfile text, deterministic for a given set of routes.

    Raises:
        ValueError: domain or cert_dir is invalid.
    """
    if not DOMAIN_RE.match(domain):
        raise ValueError(f"domain '{domain}' is not valid")
    if not CERT_DIR_RE.match(cert_dir) or ".." in cert_dir.split("/"):
        raise ValueError(f"cert_dir '{cert_dir}' must be an absolute path of [A-Za-z0-9._/-]")
    cert_dir = cert_dir.rstrip("/")
    lines = [
        "# Managed by InfraFoundry (reverse-proxy blueprint). Do not edit.",
        "{",
        "\tauto_https off",
        "}",
    ]
    for route in routes:
        lines += ["", f"https://{route.name}.{domain} {{"]
        lines.append(f"\ttls {cert_dir}/proxy.fullchain.pem {cert_dir}/proxy.key")
        if route.allow_from:
            lines.append(f"\t@blocked not remote_ip {' '.join(route.allow_from)}")
            lines.append("\tabort @blocked")
        lines.append(f"\treverse_proxy {route.backend} {{")
        if route.insecure:
            lines += ["\t\ttransport http {", "\t\t\ttls_insecure_skip_verify", "\t\t}"]
        if route.host_header == UPSTREAM:
            lines.append("\t\theader_up Host {upstream_hostport}")
        elif route.host_header:
            lines.append(f"\t\theader_up Host {route.host_header}")
        lines += ["\t}", "}"]
    return "\n".join(lines) + "\n"


def main() -> int:
    """Print the Caddyfile for the RP_* environment; return the exit code."""
    try:
        routes = parse_routes(os.environ.get("RP_ROUTES", "[]"), os.environ.get("RP_ALLOWED", "[]"))
        text = render_caddyfile(
            routes,
            os.environ.get("RP_DOMAIN", ""),
            os.environ.get("RP_CERT_DIR", "/etc/ssl/infrafoundry"),
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
