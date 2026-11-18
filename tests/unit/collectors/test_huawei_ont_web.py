"""Tests for the Huawei ONT collector."""

from __future__ import annotations

import base64
import logging

import pytest
import requests

from infrafoundry.collectors.base import CollectorAuthError, CollectorError
from infrafoundry.collectors.huawei_ont_web import HuaweiOntWebCollector

from .conftest import FakeResponse, FakeSession, MakeDevice, fixture


def _session(ok: bool = True, xml: bytes | None = None) -> FakeSession:
    page = "huawei_cfgfile_ok.html" if ok else "huawei_cfgfile_nologin.html"
    return FakeSession(
        replies={
            ("POST", "GetRandCount.asp"): FakeResponse(fixture("huawei_getrandcount.txt")),
            ("GET", "cfgfileptvdf.asp"): FakeResponse(fixture(page)),
            ("POST", "cfgfiledown.cgi"): FakeResponse(xml or fixture("huawei_config.xml")),
            ("GET", "index.asp"): FakeResponse(fixture("huawei_index.html")),
        }
    )


def test_happy_path_sequence(make_device: MakeDevice) -> None:
    s = _session()
    arts = HuaweiOntWebCollector(make_device(), lambda: s).collect()
    assert [(c["method"], c["url"].split("?")[0].rsplit("/", 1)[-1]) for c in s.calls] == [
        ("POST", "GetRandCount.asp"),
        ("POST", "login.cgi"),
        ("GET", "cfgfileptvdf.asp"),
        ("POST", "StartFileLoad.asp"),
        ("POST", "cfgfiledown.cgi"),
        ("GET", "index.asp"),
        ("POST", "logout.cgi"),
    ]
    assert arts[0].name == "config.xml" and arts[0].secret_bearing
    assert arts[0].content.startswith(b"<?xml")
    # Request details as measured on a live device.
    start = next(c for c in s.calls if "StartFileLoad" in c["url"])
    assert start["data"] == b""
    assert s.calls[-1]["url"] == "http://192.0.2.1/logout.cgi?RequestFile=html/logout.html"
    download = next(c for c in s.calls if "cfgfiledown" in c["url"])
    assert download["url"].endswith(
        "cfgfiledown.cgi?&RequestFile=html/ssmp/cfgfile/cfgfileptvdf.asp"
    )


def test_login_form_and_headers(make_device: MakeDevice) -> None:
    s = _session()
    HuaweiOntWebCollector(make_device(options={"language": "dutch"}), lambda: s).collect()
    login = next(c for c in s.calls if c["url"].endswith("login.cgi"))
    assert login["data"]["PassWord"] == base64.b64encode(b"CANARY-LOGIN-0001").decode()
    assert login["data"]["x.X_HW_Token"] == "0123abcd4567ef89"  # BOM stripped
    assert login["data"]["Language"] == "dutch"
    assert login["headers"]["Cookie"] == "Cookie=body:Language:dutch:id=-1"
    assert all(c["headers"]["Referer"] == "http://192.0.2.1/" for c in s.calls)
    download = next(c for c in s.calls if "cfgfiledown" in c["url"])
    assert download["data"]["x.X_HW_Token"] == "0123abcd4567ef89"


def test_default_language(make_device: MakeDevice) -> None:
    s = _session()
    HuaweiOntWebCollector(make_device(), lambda: s).collect()
    login = next(c for c in s.calls if c["url"].endswith("login.cgi"))
    assert login["data"]["Language"] == "english"


def test_custom_config_page(make_device: MakeDevice) -> None:
    s = _session()
    s.replies[("GET", "custom.asp")] = FakeResponse(fixture("huawei_cfgfile_ok.html"))
    HuaweiOntWebCollector(make_device(options={"config_page": "x/custom.asp"}), lambda: s).collect()
    urls = [c["url"] for c in s.calls]
    assert any(u.endswith("/x/custom.asp") for u in urls)
    assert any(u.endswith("RequestFile=x/custom.asp") for u in urls)


def test_login_failure_single_attempt_no_download(make_device: MakeDevice) -> None:
    s = _session(ok=False)
    with pytest.raises(CollectorAuthError, match="not retried"):
        HuaweiOntWebCollector(make_device(), lambda: s).collect()
    urls = [c["url"] for c in s.calls]
    assert sum(u.endswith("login.cgi") for u in urls) == 1
    assert not any("StartFileLoad" in u or "cfgfiledown" in u for u in urls)


def test_non_xml_download_logs_out_and_raises(make_device: MakeDevice) -> None:
    s = _session(xml=b"<html>error CANARY-BODY</html>")
    with pytest.raises(CollectorError, match="unexpected config download") as info:
        HuaweiOntWebCollector(make_device(), lambda: s).collect()
    assert "CANARY" not in str(info.value)
    assert "/logout.cgi?" in s.paths()[-1][1]


def test_transport_error_still_logs_out(make_device: MakeDevice) -> None:
    s = _session()
    s.replies[("POST", "cfgfiledown.cgi")] = requests.ConnectionError("boom")
    with pytest.raises(requests.ConnectionError):
        HuaweiOntWebCollector(make_device(), lambda: s).collect()
    assert "/logout.cgi?" in s.paths()[-1][1]


def test_logout_failure_does_not_mask_success(
    make_device: MakeDevice, caplog: pytest.LogCaptureFixture
) -> None:
    s = _session()
    s.replies[("POST", "logout.cgi")] = requests.ConnectionError("boom")
    with caplog.at_level(logging.DEBUG):
        arts = HuaweiOntWebCollector(make_device(), lambda: s).collect()
    assert arts
    assert "logout failed" in caplog.text


def test_logout_skipped_without_index_token(make_device: MakeDevice) -> None:
    s = _session()
    s.replies[("GET", "index.asp")] = FakeResponse(b"<html></html>")
    HuaweiOntWebCollector(make_device(), lambda: s).collect()
    assert not any("logout.cgi" in c["url"] for c in s.calls)


def test_no_secrets_logged(make_device: MakeDevice, caplog: pytest.LogCaptureFixture) -> None:
    s = _session()
    with caplog.at_level(logging.DEBUG):
        HuaweiOntWebCollector(make_device(), lambda: s).collect()
        s2 = _session(ok=False)
        with pytest.raises(CollectorAuthError):
            HuaweiOntWebCollector(make_device(), lambda: s2).collect()
    assert "CANARY" not in caplog.text


def test_mask_salted_values_masks_only_dollar_two_values() -> None:
    from infrafoundry.collectors.huawei_ont_web import mask_salted_values

    a = b'<X PreSharedKey="$2abcCANARY$" SSID="lab" Mode="$1notsalted"/>'
    b = b'<X PreSharedKey="$2xyzCANARY$" SSID="lab" Mode="$1notsalted"/>'
    assert mask_salted_values(a) == mask_salted_values(b)
    assert b'SSID="lab"' in mask_salted_values(a)
    assert b"$1notsalted" in mask_salted_values(a)


def test_config_artifact_uses_salted_value_masking(make_device: MakeDevice) -> None:
    from infrafoundry.collectors.huawei_ont_web import mask_salted_values

    s = _session()
    [art] = HuaweiOntWebCollector(make_device(), lambda: s).collect()
    assert art.compare_key is mask_salted_values


def test_mask_salted_values_masks_host_runtime_attributes() -> None:
    from infrafoundry.collectors.huawei_ont_web import mask_salted_values

    def host(mac: bytes, changed: bytes, online: bytes) -> bytes:
        return (
            b'<hostsInstance MACAddress="'
            + mac
            + b'" LastStatusChangeTime="'
            + changed
            + b'" IsOnlineFlag="'
            + online
            + b'"/>'
        )

    a = host(b"020000000001", b"2026-01-01 00:00:00", b"1")
    b = host(b"020000000001", b"2026-01-02 08:30:00", b"0")
    c = host(b"020000000002", b"2026-01-02 08:30:00", b"0")
    assert mask_salted_values(a) == mask_salted_values(b)
    assert mask_salted_values(a) != mask_salted_values(c)
