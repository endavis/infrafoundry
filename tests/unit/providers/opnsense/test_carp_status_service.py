"""Unit tests for the read-only CARP status service (#1393)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.providers.opnsense.services.carp_status import CarpStatusService


def test_vip_status_gets_the_endpoint() -> None:
    client = MagicMock()
    client.request.return_value = {"rows": [], "carp": {}}
    assert CarpStatusService(client).vip_status() == {"rows": [], "carp": {}}
    client.request.assert_called_once()
    method, path = client.request.call_args.args
    assert method == "GET"
    assert path == "diagnostics/interface/getVipStatus"


@pytest.mark.parametrize("reply", [[], "x", None])
def test_vip_status_rejects_a_non_object(reply: object) -> None:
    client = MagicMock()
    client.request.return_value = reply
    with pytest.raises(APIError, match="unexpected reply"):
        CarpStatusService(client).vip_status()
