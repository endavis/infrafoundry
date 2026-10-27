"""Tests for ``raise_on_failed_write`` (#1151).

OPNsense answers a write that fails model validation with HTTP 200 and
``{"result": "failed", "validations": {...}}``; the helper turns that into an
``APIError`` and passes every other response through.
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.core.exceptions import APIError
from infrafoundry.providers.opnsense.services.base import raise_on_failed_write


@pytest.mark.parametrize(
    "response",
    [{"result": "saved", "uuid": "u1"}, {"result": "deleted"}, {"status": "ok"}, {}, None, []],
)
def test_non_failed_responses_pass_through(response: Any) -> None:
    assert raise_on_failed_write(response, "add thing") is response


def test_failed_response_raises_with_the_validations() -> None:
    response = {"result": "failed", "validations": {"route.gateway": "Option not in list."}}

    with pytest.raises(APIError, match=r"add static route x.*Option not in list") as excinfo:
        raise_on_failed_write(response, "add static route x")

    assert excinfo.value.context["provider"] == "opnsense"


def test_failed_response_without_validations_still_raises() -> None:
    with pytest.raises(APIError, match="no validation details"):
        raise_on_failed_write({"result": "failed"}, "delete gateway GW")
