"""Tests for checksum-verified installs of HashiCorp-hosted tools (Terraform).

``releases.hashicorp.com`` is outside the implicitly trusted GitHub hosts, so
``download_and_extract_archive`` refuses it without a digest. These tests pin
that ``_install_hashicorp_zip`` looks the digest up in the release's
``SHA256SUMS`` file and passes it through (#1054).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tools.doit.install_tools import (
    IntegrityError,
    _install_hashicorp_zip,
    _install_terraform,
    fetch_sha256_from_sums,
)

SUMS = (
    "aaaa1111  terraform_1.9.0_darwin_arm64.zip\n"
    "BBBB2222  terraform_1.9.0_linux_amd64.zip\n"
    "cccc3333 *terraform_1.9.0_windows_amd64.zip\n"
)


def _urlopen_returning(body: str) -> MagicMock:
    response = MagicMock()
    response.read.return_value = body.encode()
    response.__enter__.return_value = response
    return MagicMock(return_value=response)


class TestFetchSha256FromSums:
    """``fetch_sha256_from_sums`` parses ``SHA256SUMS``-style files."""

    def test_returns_lowercase_digest_for_listed_file(self) -> None:
        with patch("tools.doit.install_tools.urllib.request.urlopen", _urlopen_returning(SUMS)):
            digest = fetch_sha256_from_sums(
                "https://example/SUMS", "terraform_1.9.0_linux_amd64.zip"
            )
        assert digest == "bbbb2222"

    def test_accepts_binary_mode_marker(self) -> None:
        with patch("tools.doit.install_tools.urllib.request.urlopen", _urlopen_returning(SUMS)):
            digest = fetch_sha256_from_sums(
                "https://example/SUMS", "terraform_1.9.0_windows_amd64.zip"
            )
        assert digest == "cccc3333"

    def test_unlisted_file_raises_integrity_error(self) -> None:
        with (
            patch("tools.doit.install_tools.urllib.request.urlopen", _urlopen_returning(SUMS)),
            pytest.raises(IntegrityError, match="not listed"),
        ):
            fetch_sha256_from_sums("https://example/SUMS", "terraform_1.9.0_linux_386.zip")


class TestInstallHashicorpZipVerifies:
    """``_install_hashicorp_zip`` passes the looked-up digest to the download."""

    def _run(self, sums_url_template: str | None) -> tuple[MagicMock, MagicMock]:
        with (
            patch("tools.doit.install_tools.get_latest_github_release", return_value="1.9.0"),
            patch("tools.doit.install_tools.shutil.which", return_value=None),
            patch("tools.doit.install_tools.platform.system", return_value="Linux"),
            patch("tools.doit.install_tools._get_arch", return_value="amd64"),
            patch("tools.doit.install_tools.get_install_dir"),
            patch(
                "tools.doit.install_tools.fetch_sha256_from_sums", return_value="bbbb2222"
            ) as fetch,
            patch("tools.doit.install_tools.download_and_extract_archive") as download,
        ):
            _install_hashicorp_zip(
                name="Terraform",
                repo="hashicorp/terraform",
                url_template="https://releases.hashicorp.com/terraform/{version}/terraform_{version}_{os}_{arch}.zip",
                binary_name="terraform",
                sums_url_template=sums_url_template,
            )
        return fetch, download

    def test_digest_from_sums_file_is_passed_to_download(self) -> None:
        fetch, download = self._run(
            "https://releases.hashicorp.com/terraform/{version}/terraform_{version}_SHA256SUMS"
        )
        fetch.assert_called_once_with(
            "https://releases.hashicorp.com/terraform/1.9.0/terraform_1.9.0_SHA256SUMS",
            "terraform_1.9.0_linux_amd64.zip",
        )
        assert download.call_args.kwargs["sha256"] == "bbbb2222"

    def test_without_sums_template_no_digest_is_passed(self) -> None:
        fetch, download = self._run(None)
        fetch.assert_not_called()
        assert download.call_args.kwargs["sha256"] is None

    def test_terraform_install_supplies_a_sums_template(self) -> None:
        with patch("tools.doit.install_tools._install_hashicorp_zip") as install:
            _install_terraform()
        template = install.call_args.kwargs["sums_url_template"]
        assert template.startswith("https://releases.hashicorp.com/terraform/{version}/")
        assert template.endswith("_SHA256SUMS")
