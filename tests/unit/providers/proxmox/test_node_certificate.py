"""``install_node_certificate``: installing on a Proxmox node through the API (#1705)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from infrafoundry.core.certs.models import CertificateInstallError
from infrafoundry.core.exceptions import APIError, AuthenticationError
from infrafoundry.providers.proxmox.node_certificate import install_node_certificate

pytestmark = pytest.mark.unit

KEY = "-----BEGIN " + "PRIVATE KEY-----\nSENTINEL-NOT-A-REAL-KEY\n-----END " + "PRIVATE KEY-----\n"


def client(nodes: list[str] | None = None) -> MagicMock:
    mock = MagicMock()
    mock.get_json.return_value = {"data": [{"node": n} for n in (nodes or ["node1", "node2"])]}
    mock.post_json.return_value = {"data": None}
    return mock


def test_it_posts_the_certificate_chain_and_key_to_the_node() -> None:
    api = client()
    install_node_certificate(api, "node1", "CERT\n", "CHAIN\n", KEY)
    api.get_json.assert_called_once_with("nodes")
    endpoint, data = api.post_json.call_args.args
    assert endpoint == "nodes/node1/certificates/custom"
    assert data == {"certificates": "CERT\nCHAIN\n", "key": KEY, "force": 1, "restart": 1}


def test_an_empty_chain_posts_the_leaf_alone() -> None:
    api = client()
    install_node_certificate(api, "node1", "CERT", "", KEY)
    assert api.post_json.call_args.args[1]["certificates"] == "CERT\n"


def test_an_unknown_node_fails_before_any_post() -> None:
    api = client(["node2"])
    with pytest.raises(CertificateInstallError, match="'node1' is not in the cluster"):
        install_node_certificate(api, "node1", "C", "", KEY)
    api.post_json.assert_not_called()


def test_a_403_names_the_missing_permission() -> None:
    api = client()
    api.post_json.side_effect = AuthenticationError(
        "Proxmox authentication failed", status_code=403, provider="proxmox"
    )
    with pytest.raises(CertificateInstallError, match=r"Sys\.Modify on /nodes/node1") as exc_info:
        install_node_certificate(api, "node1", "C", "", KEY)
    assert "403" in str(exc_info.value)


def test_a_listing_failure_is_a_install_error() -> None:
    api = MagicMock()
    api.get_json.side_effect = APIError("down", provider="proxmox")
    with pytest.raises(CertificateInstallError, match="listing nodes"):
        install_node_certificate(api, "node1", "C", "", KEY)


def test_a_server_error_does_not_leak_the_key() -> None:
    api = client()
    api.post_json.side_effect = APIError(
        "Proxmox API request failed: 500", status_code=500, response=KEY, provider="proxmox"
    )
    with pytest.raises(CertificateInstallError) as exc_info:
        install_node_certificate(api, "node1", "C", "", KEY)
    text = str(exc_info.value)
    assert "SENTINEL" not in text
    assert "500" in text
    assert "Sys.Modify" not in text
    assert exc_info.value.__cause__ is None


def test_the_key_is_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    api: Any = client()
    with caplog.at_level("DEBUG"):
        install_node_certificate(api, "node1", "C", "", KEY)
    assert "SENTINEL" not in caplog.text
