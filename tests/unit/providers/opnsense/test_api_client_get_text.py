"""Unit tests for ``OPNsenseClient.get_text`` (#1497)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from opnsense_openapi import APIResponseError

from infrafoundry.core.exceptions import APIError, AuthenticationError
from infrafoundry.providers.opnsense.api_client import OPNsenseClient

_UNDERLYING_CLIENT = "infrafoundry.providers.opnsense.api_client.OpenAPIOPNsenseClient"
_SECRET_BODY = "<opnsense><secret>hunter2-synthetic</secret></opnsense>"


def _client(mock_cls: MagicMock) -> tuple[OPNsenseClient, MagicMock]:
    client = OPNsenseClient(api_key="k", api_secret="s", base_url="https://opnsense.example")
    return client, mock_cls.return_value


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://opnsense.example/api/core/backup/download/this")
    response = httpx.Response(status, text=_SECRET_BODY, request=request)
    return httpx.HTTPStatusError("failed", request=request, response=response)


def test_returns_the_body_verbatim() -> None:
    with patch(_UNDERLYING_CLIENT) as mock_cls:
        client, underlying = _client(mock_cls)
        underlying.get.side_effect = APIResponseError("not json", _SECRET_BODY)
        assert client.get_text("core/backup/download/this") == _SECRET_BODY
        underlying.get.assert_called_once_with("core", "backup", "download", "this")
        underlying.post.assert_not_called()


def test_forwards_query_params() -> None:
    with patch(_UNDERLYING_CLIENT) as mock_cls:
        client, underlying = _client(mock_cls)
        underlying.get.side_effect = APIResponseError("not json", "x")
        client.get_text("core/backup/download/this", params={"a": "1"})
        underlying.get.assert_called_once_with("core", "backup", "download", "this", a="1")


def test_json_body_is_an_error_without_the_body() -> None:
    with patch(_UNDERLYING_CLIENT) as mock_cls:
        client, underlying = _client(mock_cls)
        underlying.get.return_value = {"secret": "hunter2-synthetic"}
        with pytest.raises(APIError) as excinfo:
            client.get_text("core/backup/download/this")
    assert "hunter2" not in str(excinfo.value)
    assert excinfo.value.response is None


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failures_map_to_authentication_error(status: int) -> None:
    with patch(_UNDERLYING_CLIENT) as mock_cls:
        client, underlying = _client(mock_cls)
        underlying.get.side_effect = _status_error(status)
        with pytest.raises(AuthenticationError) as excinfo:
            client.get_text("core/backup/download/this")
    assert excinfo.value.status_code == status
    assert excinfo.value.response is None
    assert "hunter2" not in str(excinfo.value)


def test_other_http_errors_map_to_api_error_without_the_body() -> None:
    with patch(_UNDERLYING_CLIENT) as mock_cls:
        client, underlying = _client(mock_cls)
        underlying.get.side_effect = _status_error(500)
        with pytest.raises(APIError) as excinfo:
            client.get_text("core/backup/download/this")
    assert not isinstance(excinfo.value, AuthenticationError)
    assert excinfo.value.status_code == 500
    assert excinfo.value.response is None
    assert "hunter2" not in str(excinfo.value)


def test_short_endpoint_is_rejected() -> None:
    with patch(_UNDERLYING_CLIENT) as mock_cls:
        client, _ = _client(mock_cls)
        with pytest.raises(ValueError, match="Invalid endpoint"):
            client.get_text("core/backup")
