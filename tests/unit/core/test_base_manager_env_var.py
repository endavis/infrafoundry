"""``PathBasedManager._get_env_var`` must not log environment variable values.

The helper logged ``value=<value>`` at debug level, so a manager reading a
secret through it wrote the secret to the log in clear text (CodeQL
"clear-text logging of sensitive information", surfaced in #1056).
"""

from __future__ import annotations

import logging

import pytest

from infrafoundry.core.base_manager import PathBasedManager

SECRET = "s3cr3t-token-value"


class _Manager(PathBasedManager):
    def cleanup(self) -> None:
        pass


def test_value_is_returned_but_not_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("INFRAFOUNDRY_TEST_TOKEN", SECRET)

    with caplog.at_level(logging.DEBUG):
        value = _Manager()._get_env_var("INFRAFOUNDRY_TEST_TOKEN")

    assert value == SECRET
    assert "INFRAFOUNDRY_TEST_TOKEN" in caplog.text
    assert SECRET not in caplog.text


def test_unset_variable_returns_none_without_logging(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("INFRAFOUNDRY_TEST_TOKEN", raising=False)

    with caplog.at_level(logging.DEBUG):
        value = _Manager()._get_env_var("INFRAFOUNDRY_TEST_TOKEN")

    assert value is None
    assert "INFRAFOUNDRY_TEST_TOKEN" not in caplog.text
