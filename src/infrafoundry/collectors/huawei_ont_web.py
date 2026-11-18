"""Collector for Huawei ONT web UIs (HG8xxx family).

One login attempt per run, one session, always logs out. These units lock the login after
a few failures, so a failed login is never retried. Bodies, tokens and the password are
never logged.
"""

from __future__ import annotations

import base64
import logging
import re
from collections.abc import Callable
from typing import Any

import requests

from infrafoundry.core.config.models import CollectorDeviceConfig

from .base import Artifact, CollectorAuthError, CollectorError

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "english"
DEFAULT_CONFIG_PAGE = "html/ssmp/cfgfile/cfgfileptvdf.asp"
# The ONT stores secrets as "$2...$" values and re-salts them on every export, and its
# LAN host table carries runtime state. Two exports of an unchanged device differ only
# in these, so change detection masks them.
_SALTED_VALUE_RE = re.compile(rb'"\$2[^"]*"')
_RUNTIME_ATTR_RE = re.compile(rb'\b(LastStatusChangeTime|IsOnlineFlag)="[^"]*"')
_ONTTOKEN_RE = re.compile(r'id="onttoken"\s+value="([0-9a-fA-F]+)"')
_XML_STARTS = (b"<?xml", b"<Inte")


def mask_salted_values(content: bytes) -> bytes:
    """Mask what the ONT regenerates on every export, for change detection.

    That is the re-salted ``$2...$`` secret values and the LAN host table's
    ``LastStatusChangeTime``/``IsOnlineFlag`` runtime attributes. A change to only
    these is therefore not reported as a change.
    """
    masked = _SALTED_VALUE_RE.sub(b'"$2<salted>"', content)
    return _RUNTIME_ATTR_RE.sub(rb'\1="<runtime>"', masked)


class HuaweiOntWebCollector:
    """Downloads the plain config export of a Huawei ONT through its web UI."""

    def __init__(
        self,
        device: CollectorDeviceConfig,
        session_factory: Callable[[], Any] = requests.Session,
    ) -> None:
        """Initialize the collector.

        Args:
            device: Resolved device config (``address`` is the base URL).
            session_factory: Builds the HTTP session; injectable for tests.
        """
        self._device = device
        self._base = device.address.rstrip("/")
        self._session = session_factory()
        self._language = str(device.options.get("language", DEFAULT_LANGUAGE))
        self._page = str(device.options.get("config_page", DEFAULT_CONFIG_PAGE))

    def _request(
        self, method: str, path: str, *, data: dict[str, str] | bytes | None = None, **kw: Any
    ) -> Any:
        headers = {"Referer": f"{self._base}/", **kw.pop("headers", {})}
        return self._session.request(
            method,
            f"{self._base}/{path.lstrip('/')}",
            data=data,
            headers=headers,
            timeout=self._device.timeout,
            verify=self._device.verify_ssl,
            allow_redirects=False,
            **kw,
        )

    def _token(self) -> str:
        response = self._request("POST", "asp/GetRandCount.asp")
        return bytes(response.content).decode("utf-8-sig").strip()

    def _page_token(self, html: bytes) -> str | None:
        match = _ONTTOKEN_RE.search(html.decode("utf-8", errors="replace"))
        return match.group(1) if match else None

    def collect(self) -> list[Artifact]:
        """Log in once, download the config and log out.

        Raises:
            CollectorAuthError: If the login produced no page token.
            CollectorError: If the download is not an XML config.
        """
        password = base64.b64encode((self._device.password or "").encode()).decode()
        try:
            return [self._download(password)]
        finally:
            self._logout()

    def _download(self, password_b64: str) -> Artifact:
        form = {
            "UserName": self._device.username or "",
            "PassWord": password_b64,
            "Language": self._language,
            "x.X_HW_Token": self._token(),
        }
        self._request(
            "POST",
            "login.cgi",
            data=form,
            headers={"Cookie": f"Cookie=body:Language:{self._language}:id=-1"},
        )
        page = self._request("GET", self._page)
        token = self._page_token(bytes(page.content))
        if token is None:
            raise CollectorAuthError(
                f"{self._device.name}: login failed; not retried "
                "(device locks after repeated failures)"
            )
        self._request("POST", "html/ssmp/common/StartFileLoad.asp", data=b"")
        response = self._request(
            "POST",
            f"cfgfiledown.cgi?&RequestFile={self._page}",
            data={"x.X_HW_Token": token},
        )
        body = bytes(response.content).lstrip(b"\xef\xbb\xbf").lstrip()
        if not body.startswith(_XML_STARTS):
            raise CollectorError(f"{self._device.name}: unexpected config download response")
        return Artifact("config.xml", body, secret_bearing=True, compare_key=mask_salted_values)

    def _logout(self) -> None:
        try:
            index = self._request("GET", "index.asp")
            token = self._page_token(bytes(index.content))
            if token is not None:
                self._request(
                    "POST",
                    "logout.cgi?RequestFile=html/logout.html",
                    data={"x.X_HW_Token": token},
                )
        except Exception as exc:  # logout must never mask the original outcome
            logger.warning("%s: logout failed (%s)", self._device.name, type(exc).__name__)
