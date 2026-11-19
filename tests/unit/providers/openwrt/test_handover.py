"""Tests for the ucode helper that replays CLI-staged UCI changes into an rpcd session."""

import shutil
import subprocess
from importlib import resources

import pytest

HELPER = resources.files("infrafoundry.providers.openwrt").joinpath("files", "handover.uc")


def _source() -> str:
    return HELPER.read_text(encoding="utf-8")


def test_helper_is_packaged_next_to_the_provider() -> None:
    assert HELPER.is_file()
    assert "{{" not in _source()


@pytest.mark.parametrize("op", ["add", "set", "remove", "list-add", "list-del"])
def test_helper_replays_each_supported_op(op: str) -> None:
    assert f"'{op}'" in _source()


def test_helper_dies_on_unsupported_ops_and_failures() -> None:
    source = _source()
    assert "unsupported staged change" in source
    assert "rename" in source and "order" in source
    assert "die(sprintf('ubus uci" in source


def test_helper_reverts_cli_staging_after_the_ops_and_validates_the_session() -> None:
    source = _source()
    assert source.index("cur.revert(config)") > source.index("unsupported staged change")
    assert "[0-9a-f]{32}" in source
    assert "replayed" in source


def test_helper_treats_a_missing_list_as_empty() -> None:
    assert "as_list(reply?.value)" in _source()


@pytest.mark.skipif(shutil.which("ucode") is None, reason="ucode is not installed")
def test_helper_rejects_a_bad_session_id_when_ucode_is_available() -> None:
    result = subprocess.run(
        ["ucode", str(HELPER), "not-a-session", "network"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
