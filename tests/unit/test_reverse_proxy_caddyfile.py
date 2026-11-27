"""Tests for blueprints/reverse-proxy/scripts/reverse-proxy-caddyfile.py (#1689)."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "blueprints" / "reverse-proxy" / "scripts" / "reverse-proxy-caddyfile.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("reverse_proxy_caddyfile", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["reverse_proxy_caddyfile"] = mod
    spec.loader.exec_module(mod)
    return mod


rp: Any = _load()

CERT_DIR = "/etc/ssl/infrafoundry"


def _render(routes: list[dict[str, Any]], allowed: list[str] | None = None) -> str:
    parsed = rp.parse_routes(json.dumps(routes), json.dumps(allowed or []))
    return str(rp.render_caddyfile(parsed, "example.com", CERT_DIR))


def test_global_block_turns_automatic_https_off() -> None:
    text = _render([{"name": "nas", "backend": "https://192.0.2.20"}])

    assert text.startswith("# Managed by InfraFoundry")
    assert "{\n\tauto_https off\n}" in text


def test_site_block_uses_the_installed_certificate() -> None:
    text = _render([{"name": "nas", "backend": "http://192.0.2.20:8080"}])

    assert "https://nas.example.com {" in text
    assert f"tls {CERT_DIR}/proxy.fullchain.pem {CERT_DIR}/proxy.key" in text
    assert "reverse_proxy http://192.0.2.20:8080 {" in text


def test_insecure_only_on_insecure_routes() -> None:
    text = _render(
        [
            {"name": "a", "backend": "https://192.0.2.20", "insecure": True},
            {"name": "b", "backend": "https://192.0.2.21"},
        ]
    )

    assert text.count("tls_insecure_skip_verify") == 1
    assert text.index("tls_insecure_skip_verify") < text.index("https://b.example.com")


def test_host_header_upstream_and_literal() -> None:
    text = _render(
        [
            {"name": "a", "backend": "https://192.0.2.20", "host_header": "upstream"},
            {"name": "b", "backend": "https://192.0.2.21", "host_header": "ui.example.net"},
            {"name": "c", "backend": "https://192.0.2.22"},
        ]
    )

    assert "header_up Host {upstream_hostport}" in text
    assert "header_up Host ui.example.net" in text
    assert text.count("header_up") == 2


def test_allow_from_and_the_allowed_networks_fallback() -> None:
    text = _render(
        [
            {"name": "a", "backend": "https://192.0.2.20", "allow_from": ["198.51.100.0/24"]},
            {"name": "b", "backend": "https://192.0.2.21"},
        ],
        allowed=["192.0.2.0/24"],
    )

    assert "@blocked not remote_ip 198.51.100.0/24" in text
    assert "@blocked not remote_ip 192.0.2.0/24" in text
    assert text.count("abort @blocked") == 2


def test_no_restriction_when_both_lists_are_empty() -> None:
    text = _render([{"name": "a", "backend": "https://192.0.2.20"}])

    assert "remote_ip" not in text
    assert "abort" not in text


def test_output_is_deterministic_regardless_of_order() -> None:
    a = {"name": "a", "backend": "https://192.0.2.20"}
    b = {"name": "b", "backend": "https://192.0.2.21"}

    assert _render([a, b]) == _render([b, a])


def test_no_routes_render_only_the_global_block() -> None:
    assert "https://" not in _render([])


@pytest.mark.parametrize(
    ("route", "message"),
    [
        ({"name": "Bad_Name", "backend": "https://192.0.2.20"}, "DNS label"),
        ({"name": "-a", "backend": "https://192.0.2.20"}, "DNS label"),
        ({"name": "a", "backend": "ftp://192.0.2.20"}, "http"),
        ({"name": "a", "backend": "https://192.0.2.20 {"}, "forbidden"),
        ({"name": "a", "backend": "https://192.0.2.20}"}, "forbidden"),
        ({"name": "a", "backend": "https://192.0.2.20\nrespond"}, "forbidden"),
        ({"name": "a", "backend": "https://192.0.2.20/path"}, "path"),
        ({"name": "a", "backend": "http://192.0.2.20", "insecure": True}, "https backend"),
        ({"name": "a", "backend": "https://192.0.2.20", "insecure": "yes"}, "true or false"),
        ({"name": "a", "backend": "https://192.0.2.20", "allow_from": ["nope"]}, "not a CIDR"),
        ({"name": "a", "backend": "https://192.0.2.20", "host_header": "a b"}, "host_header"),
        ({"name": "a", "backend": "https://192.0.2.20", "host_header": "x{y}"}, "host_header"),
    ],
)
def test_bad_routes_are_rejected_with_the_route_named(route: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message) as err:
        _render([route])

    assert str(route["name"]) in str(err.value)


def test_duplicate_names_are_rejected() -> None:
    route = {"name": "a", "backend": "https://192.0.2.20"}

    with pytest.raises(ValueError, match="not unique"):
        _render([route, route])


@pytest.mark.parametrize("cert_dir", ["relative/dir", "/etc/ssl/a b", "/etc/../x", "/x;id"])
def test_bad_cert_dir_is_rejected(cert_dir: str) -> None:
    with pytest.raises(ValueError, match="cert_dir"):
        rp.render_caddyfile([], "example.com", cert_dir)


def test_bad_domain_is_rejected() -> None:
    with pytest.raises(ValueError, match="domain"):
        rp.render_caddyfile([], "example.com\nrespond", CERT_DIR)


def test_main_exits_non_zero_with_the_message_on_stderr() -> None:
    env = {
        **os.environ,
        "RP_ROUTES": json.dumps([{"name": "a", "backend": "ftp://x"}]),
        "RP_DOMAIN": "example.com",
    }
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 1
    assert "route 'a'" in result.stderr
    assert result.stdout == ""


@pytest.mark.skipif(shutil.which("caddy") is None, reason="caddy is not installed")
def test_caddy_validates_the_rendered_output(tmp_path: Path) -> None:
    cert = tmp_path / "proxy.fullchain.pem"
    key = tmp_path / "proxy.key"
    subprocess.run(
        [
            *("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes"),
            *("-subj", "/CN=nas.example.com"),
            *("-keyout", str(key), "-out", str(cert), "-days", "1"),
        ],
        check=True,
        capture_output=True,
    )
    parsed = rp.parse_routes(
        json.dumps(
            [
                {
                    "name": "nas",
                    "backend": "https://192.0.2.20",
                    "insecure": True,
                    "host_header": "upstream",
                    "allow_from": ["192.0.2.0/24"],
                }
            ]
        ),
        "[]",
    )
    caddyfile = tmp_path / "Caddyfile"
    caddyfile.write_text(rp.render_caddyfile(parsed, "example.com", str(tmp_path)))

    result = subprocess.run(
        ["caddy", "validate", "--adapter", "caddyfile", "--config", str(caddyfile)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
