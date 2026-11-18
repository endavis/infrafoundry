"""Tests for the RouterOS REST client."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from infrafoundry.providers.mikrotik.client import (
    RouterOSAPIError,
    RouterOSClient,
    RouterOSConnectionError,
)
from infrafoundry.providers.mikrotik.settings import MikroTikSettings

PASSWORD = "pw-example-0123"
SETTINGS = MikroTikSettings("https://192.0.2.2", "admin", PASSWORD, verify_ssl=False, timeout=7)


def _response(status: int, body: Any) -> MagicMock:
    response = MagicMock(spec=requests.Response)
    response.status_code = status
    response.json.return_value = body
    return response


def test_get_builds_url_with_auth_verify_and_timeout() -> None:
    client = RouterOSClient(SETTINGS)
    with patch.object(
        requests.Session, "request", return_value=_response(200, [{"name": "bridge"}])
    ) as request:
        rows = client.get("interface/bridge")

    assert rows == [{"name": "bridge"}]
    assert request.call_args.args == ("GET", "https://192.0.2.2/rest/interface/bridge")
    assert request.call_args.kwargs["timeout"] == 7
    assert client._session.auth == ("admin", PASSWORD)
    assert client._session.verify is False


def test_single_object_response_is_wrapped() -> None:
    client = RouterOSClient(SETTINGS)
    with patch.object(
        requests.Session, "request", return_value=_response(200, {"version": "7.14"})
    ):
        assert client.get("system/resource") == [{"version": "7.14"}]


def test_execute_posts_script_and_returns_ret() -> None:
    client = RouterOSClient(SETTINGS)
    with patch.object(requests.Session, "request", return_value=_response(200, {"ret": "ok"})) as r:
        assert client.execute(":put ok") == "ok"
    assert r.call_args.args == ("POST", "https://192.0.2.2/rest/execute")
    assert r.call_args.kwargs["json"] == {"script": ":put ok", "as-string": True}


def test_error_carries_detail_without_credentials() -> None:
    client = RouterOSClient(SETTINGS)
    body = {"error": 400, "message": "Bad Request", "detail": "invalid value"}
    with (
        patch.object(requests.Session, "request", return_value=_response(400, body)),
        pytest.raises(RouterOSAPIError) as exc,
    ):
        client.get("interface/bridge")

    assert exc.value.status_code == 400
    assert "Bad Request" in str(exc.value)
    assert "invalid value" in str(exc.value)
    assert PASSWORD not in str(exc.value)


def test_401_raises_api_error() -> None:
    client = RouterOSClient(SETTINGS)
    with (
        patch.object(requests.Session, "request", return_value=_response(401, {})),
        pytest.raises(RouterOSAPIError) as exc,
    ):
        client.get("system/resource")
    assert exc.value.status_code == 401


def test_connection_error_is_wrapped_without_credentials() -> None:
    client = RouterOSClient(SETTINGS)
    with (
        patch.object(
            requests.Session, "request", side_effect=requests.ConnectionError(f"boom {PASSWORD}")
        ),
        pytest.raises(RouterOSConnectionError) as exc,
    ):
        client.get("system/resource")
    assert PASSWORD not in str(exc.value)


def test_put_creates_a_row_and_returns_its_id() -> None:
    client = RouterOSClient(SETTINGS)
    body = {"name": "bridge"}
    with patch.object(
        requests.Session, "request", return_value=_response(201, {".id": "*9", "name": "bridge"})
    ) as request:
        row = client.put("interface/bridge", body)

    assert row == {".id": "*9", "name": "bridge"}
    assert request.call_args.args == ("PUT", "https://192.0.2.2/rest/interface/bridge")
    assert request.call_args.kwargs["json"] == body


def test_patch_addresses_the_row_by_id() -> None:
    client = RouterOSClient(SETTINGS)
    with patch.object(
        requests.Session, "request", return_value=_response(200, {".id": "*41"})
    ) as request:
        client.patch("ip/service", "*41", {"disabled": "true"})

    assert request.call_args.args == ("PATCH", "https://192.0.2.2/rest/ip/service/*41")
    assert request.call_args.kwargs["json"] == {"disabled": "true"}


@pytest.mark.parametrize("status", [204, 200])
def test_delete_accepts_an_empty_body(status: int) -> None:
    client = RouterOSClient(SETTINGS)
    response = _response(status, None)
    response.content = b""
    response.json.side_effect = ValueError("no body")
    with patch.object(requests.Session, "request", return_value=response) as request:
        client.delete("interface/vlan", "*7")

    assert request.call_args.args == ("DELETE", "https://192.0.2.2/rest/interface/vlan/*7")
    response.json.assert_not_called()


def test_write_error_carries_message_and_detail_without_credentials() -> None:
    client = RouterOSClient(SETTINGS)
    body = {"error": 400, "message": "Bad Request", "detail": "failure: already have such entry"}
    with (
        patch.object(requests.Session, "request", return_value=_response(400, body)),
        pytest.raises(RouterOSAPIError) as exc,
    ):
        client.put("interface/vlan", {"name": "vlan10", "comment": PASSWORD})

    assert "already have such entry" in str(exc.value)
    assert PASSWORD not in str(exc.value)


def test_put_with_a_non_object_response_returns_empty() -> None:
    client = RouterOSClient(SETTINGS)
    with patch.object(requests.Session, "request", return_value=_response(200, [])):
        assert client.put("interface/bridge", {}) == {}
