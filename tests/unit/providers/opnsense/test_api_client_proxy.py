"""Unit tests for the OPNsense API client wrapper.

Covers that the optional ``proxy`` argument is forwarded to the underlying
``opnsense-openapi`` client (and defaults to ``None`` for a direct connection).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from opnsense_openapi import APIResponseError

from infrafoundry.core.exceptions import APIError
from infrafoundry.providers.opnsense.api_client import OPNsenseClient

_UNDERLYING_CLIENT = "infrafoundry.providers.opnsense.api_client.OpenAPIOPNsenseClient"


def test_proxy_forwarded_to_underlying_client() -> None:
    """A configured proxy URL is passed through to the opnsense-openapi client."""
    with patch(_UNDERLYING_CLIENT) as mock_cls:
        OPNsenseClient(
            api_key="k",
            api_secret="s",
            base_url="https://opnsense.example",
            verify_ssl=False,
            proxy="socks5://127.0.0.1:1080",
        )
    _, kwargs = mock_cls.call_args
    assert kwargs["proxy"] == "socks5://127.0.0.1:1080"


def test_proxy_defaults_to_none() -> None:
    """Omitting ``proxy`` forwards ``None`` (direct connection, unchanged behavior)."""
    with patch(_UNDERLYING_CLIENT) as mock_cls:
        OPNsenseClient(
            api_key="k",
            api_secret="s",
            base_url="https://opnsense.example",
        )
    _, kwargs = mock_cls.call_args
    assert kwargs["proxy"] is None


def test_detect_version_returns_library_value() -> None:
    """``detect_version`` delegates to the opnsense-openapi client."""
    with patch(_UNDERLYING_CLIENT) as mock_cls:
        mock_cls.return_value.detect_version.return_value = "26.1.6_2"
        client = OPNsenseClient(api_key="k", api_secret="s", base_url="https://opnsense.example")
        assert client.detect_version() == "26.1.6_2"


def test_detect_version_wraps_library_errors() -> None:
    """A library ``APIResponseError`` surfaces as the provider's ``APIError``."""
    with patch(_UNDERLYING_CLIENT) as mock_cls:
        mock_cls.return_value.detect_version.side_effect = APIResponseError("no version", "")
        client = OPNsenseClient(api_key="k", api_secret="s", base_url="https://opnsense.example")
        with pytest.raises(APIError) as excinfo:
            client.detect_version()
    assert excinfo.value.provider == "opnsense"
