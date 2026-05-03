"""Unit tests for the live → typed config projector (#720).

Target: ``infrafoundry.providers.opnsense.services.interface_assignment.
_parse_live_to_config`` and its IPv4/IPv6 sub-projectors.

Coverage:
    - Single-stack static-v4 / static-v6.
    - Dual-stack (both static).
    - DHCP v4 / DHCP v6.
    - Track-interface IPv6 (with track6-interface field present).
    - Empty (none) v4 + v6.
    - Unmapped modes (PPPoE, L2TP, GIF, GRE) raise loud ValueError.
    - Track-interface missing the track6-interface field raises.
    - Static missing subnet raises (operator must provide).
"""

from __future__ import annotations

from typing import Any

import pytest

from infrafoundry.providers.opnsense.services.interface_assignment import (
    LiveInterfaceAssignment,
    _parse_live_to_config,
)


def _live(
    identifier: str = "opt5",
    device: str = "igc0",
    *,
    ipv4: dict[str, Any] | None = None,
    ipv6: dict[str, Any] | None = None,
) -> LiveInterfaceAssignment:
    return LiveInterfaceAssignment(
        identifier=identifier,
        device=device,
        description="x",
        is_physical=True,
        ipv4=ipv4 if ipv4 is not None else {},
        ipv6=ipv6 if ipv6 is not None else {},
        macaddr="",
        mtu=1500,
    )


class TestParseLiveToConfigHappyPath:
    def test_static_v4_only(self) -> None:
        live = _live(ipv4={"ipaddr": "10.0.0.1", "subnet": "24"})
        cfg = _parse_live_to_config(live)
        assert cfg.ipv4_type == "static"
        assert cfg.ipv4_address == "10.0.0.1"
        assert cfg.ipv4_subnet == 24
        assert cfg.ipv6_type == "none"

    def test_static_v6_only(self) -> None:
        live = _live(ipv6={"ipaddrv6": "fd00::1", "subnetv6": "64"})
        cfg = _parse_live_to_config(live)
        assert cfg.ipv6_type == "static"
        assert cfg.ipv6_address == "fd00::1"
        assert cfg.ipv6_subnet == 64
        assert cfg.ipv4_type == "none"

    def test_dual_stack(self) -> None:
        live = _live(
            ipv4={"ipaddr": "10.0.0.1", "subnet": "24"},
            ipv6={"ipaddrv6": "fd00::1", "subnetv6": "64"},
        )
        cfg = _parse_live_to_config(live)
        assert cfg.ipv4_type == "static"
        assert cfg.ipv6_type == "static"

    def test_dhcp_v4(self) -> None:
        live = _live(ipv4={"ipaddr": "dhcp"})
        cfg = _parse_live_to_config(live)
        assert cfg.ipv4_type == "dhcp"
        assert cfg.ipv4_address is None
        assert cfg.ipv4_subnet is None

    def test_dhcp_v6(self) -> None:
        live = _live(ipv6={"ipaddrv6": "dhcp6"})
        cfg = _parse_live_to_config(live)
        assert cfg.ipv6_type == "dhcp"

    def test_track_interface(self) -> None:
        live = _live(ipv6={"ipaddrv6": "track6", "track6-interface": "wan"})
        cfg = _parse_live_to_config(live)
        assert cfg.ipv6_type == "track-interface"
        assert cfg.ipv6_track == "wan"

    def test_track_interface_alt_token(self) -> None:
        # The mapper accepts the long-form ``track-interface`` alias too;
        # depends on which OPNsense build emits which token.
        live = _live(ipv6={"ipaddrv6": "track-interface", "track6-interface": "wan"})
        cfg = _parse_live_to_config(live)
        assert cfg.ipv6_type == "track-interface"
        assert cfg.ipv6_track == "wan"

    def test_none(self) -> None:
        live = _live()
        cfg = _parse_live_to_config(live)
        assert cfg.ipv4_type == "none"
        assert cfg.ipv6_type == "none"

    def test_lock_and_enabled_threaded_through(self) -> None:
        # Both kwargs are forwarded onto the projected typed config so
        # diff equality after projection round-trips correctly.
        live = _live()
        cfg = _parse_live_to_config(live, lock=True, enabled=False)
        assert cfg.lock is True
        assert cfg.enabled is False


class TestParseLiveToConfigErrorPaths:
    def test_unmapped_v4_mode_raises(self) -> None:
        live = _live(ipv4={"ipaddr": "pppoe"})
        with pytest.raises(ValueError, match="unsupported IPv4 mode"):
            _parse_live_to_config(live)

    def test_unmapped_v6_mode_raises(self) -> None:
        live = _live(ipv6={"ipaddrv6": "l2tp"})
        with pytest.raises(ValueError, match="unsupported IPv6 mode"):
            _parse_live_to_config(live)

    def test_unmapped_v6_gif_raises(self) -> None:
        live = _live(ipv6={"ipaddrv6": "gif0"})
        with pytest.raises(ValueError, match="unsupported IPv6 mode"):
            _parse_live_to_config(live)

    def test_track_interface_missing_track6_field_raises(self) -> None:
        live = _live(ipv6={"ipaddrv6": "track6"})
        with pytest.raises(ValueError, match="track6-interface"):
            _parse_live_to_config(live)

    def test_static_v4_missing_subnet_raises(self) -> None:
        live = _live(ipv4={"ipaddr": "10.0.0.1"})
        with pytest.raises(ValueError, match="subnet"):
            _parse_live_to_config(live)

    def test_static_v6_missing_subnet_raises(self) -> None:
        live = _live(ipv6={"ipaddrv6": "fd00::1"})
        with pytest.raises(ValueError, match="subnetv6"):
            _parse_live_to_config(live)

    def test_static_v4_non_integer_subnet_raises(self) -> None:
        live = _live(ipv4={"ipaddr": "10.0.0.1", "subnet": "not-a-number"})
        with pytest.raises(ValueError, match="not an integer"):
            _parse_live_to_config(live)

    def test_static_v6_non_integer_subnet_raises(self) -> None:
        live = _live(ipv6={"ipaddrv6": "fd00::1", "subnetv6": "not-a-number"})
        with pytest.raises(ValueError, match="not an integer"):
            _parse_live_to_config(live)
