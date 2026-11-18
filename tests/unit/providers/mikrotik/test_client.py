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
