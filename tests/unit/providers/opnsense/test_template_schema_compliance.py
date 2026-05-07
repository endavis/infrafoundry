"""Parameterized regression tests asserting that every terraform argument
emitted by an OPNsense `*.tf.j2` template is a supported attribute of the
target `browningluke/opnsense` resource type.

Catches three classes of recurrence at PR-time (rather than at apply-time
on a live OPNsense box, see #765):

1. Wrong argument name (e.g. `rr` instead of `type`).
2. Argument with no provider equivalent (e.g. the dropped `counters`).
3. Resource type that doesn't exist in the provider (e.g. the still-broken
   `opnsense_dhcpv4_static_map` referenced by `dhcp_static_maps.tf.j2`,
   which is out of scope for this PR — see TODO below).

The schema fixture is a pinned snapshot of the provider's
`terraform providers schema -json` output. See
`tests/unit/providers/opnsense/fixtures/README.md` for regeneration
instructions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.providers.opnsense import OPNsenseProvider

# Match HCL argument assignments. Captures the argument name on lines like
# ``  hostname = "foo"`` or ``  pools = [`` or ``  subnet_id = opnsense_kea_subnet.x.id``.
# Sufficient for the scalar / list / reference forms the OPNsense templates
# emit; we deliberately avoid pulling in `python-hcl2` for this scope (#765).
_HCL_ARG_RE = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*=", re.MULTILINE)

# Match ``resource "<type>" "<name>" {`` block headers.
_HCL_RESOURCE_BLOCK_RE = re.compile(
    r'resource\s+"([a-z_][a-z0-9_]*)"\s+"[a-z_][a-z0-9_]*"\s*\{',
)

_FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SCHEMA_FIXTURE_PATH = _FIXTURES_DIR / "browningluke_opnsense_schema.json"


def _load_schema() -> dict[str, set[str]]:
    """Load the pinned provider schema fixture as resource_type -> attrs set."""
    with _SCHEMA_FIXTURE_PATH.open() as fh:
        raw: dict[str, list[str]] = json.load(fh)
    return {resource_type: set(attrs) for resource_type, attrs in raw.items()}


def _extract_resource_blocks(content: str) -> list[tuple[str, str]]:
    """Extract `(resource_type, block_body)` tuples from rendered HCL.

    The body runs from the opening `{` to the matching closing `}`. The
    OPNsense templates don't emit nested blocks, so a depth-counted scan
    is sufficient and cheaper than a full HCL parse.
    """
    blocks: list[tuple[str, str]] = []
    for match in _HCL_RESOURCE_BLOCK_RE.finditer(content):
        resource_type = match.group(1)
        # Find the matching closing brace by depth-counting from the `{`.
        body_start = match.end()
        depth = 1
        i = body_start
        while i < len(content) and depth > 0:
            ch = content[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
        body = content[body_start : i - 1]
        blocks.append((resource_type, body))
    return blocks


# Each fixture exercises every conditional branch in the corresponding
# template, so the schema-compliance test would catch a wrong-arg-name
# regression on any optional path.
#
# The `aliases` template was retired in #775 — `firewall_alias` is now
# managed via `OPNsenseDirectRunner` (no terraform path); the parameter
# was removed from the parametrize list below.


def _kea_subnet_resources() -> list[ResourceConfig]:
    return [
        ResourceConfig(
            provider="opnsense",
            type="kea_subnet",
            name="subnet-min",
            config={"subnet": "192.168.10.0/24"},
        ),
        # Exercises every conditional branch in the kea_subnet template.
        ResourceConfig(
            provider="opnsense",
            type="kea_subnet",
            name="subnet-full",
            config={
                "subnet": "192.168.20.0/24",
                "pools": ["192.168.20.100-192.168.20.200"],
                "match_client_id": True,
                "auto_collect": False,
                "routers": ["192.168.20.1"],
                "dns_servers": ["192.168.20.1"],
                "domain_name": "example.com",
                "domain_search": ["example.com", "internal.example.com"],
                "ntp_servers": ["192.168.20.1"],
                "description": "full-coverage subnet",
            },
        ),
    ]


def _kea_reservation_resources() -> list[ResourceConfig]:
    # Reservation needs its parent subnet rendered too (the template
    # references `opnsense_kea_subnet.<name>.id`); pass both so
    # `generate_terraform` writes both files.
    parent_subnet = ResourceConfig(
        provider="opnsense",
        type="kea_subnet",
        name="reservation-parent",
        config={"subnet": "192.168.30.0/24"},
    )
    minimal = ResourceConfig(
        provider="opnsense",
        type="kea_reservation",
        name="res-min",
        config={
            "subnet_ref": "reservation-parent",
            "hw_address": "00:11:22:33:44:55",
            "ip_address": "192.168.30.10",
        },
    )
    full = ResourceConfig(
        provider="opnsense",
        type="kea_reservation",
        name="res-full",
        config={
            "subnet_ref": "reservation-parent",
            "hw_address": "aa:bb:cc:dd:ee:ff",
            "ip_address": "192.168.30.20",
            "hostname": "explicit-hostname",
            "description": "with-description reservation",
        },
    )
    return [parent_subnet, minimal, full]


def _unbound_host_override_resources() -> list[ResourceConfig]:
    return [
        # Minimal — only required args.
        ResourceConfig(
            provider="opnsense",
            type="unbound_host_override",
            name="uho-min",
            config={"hostname": "min", "domain": "example.com"},
        ),
        # AAAA record — exercises the renamed `type` arg (was `rr`).
        ResourceConfig(
            provider="opnsense",
            type="unbound_host_override",
            name="uho-aaaa",
            config={
                "hostname": "v6",
                "domain": "example.com",
                "server": "2001:db8::10",
                "rr": "AAAA",
                "enabled": True,
                "description": "AAAA record",
            },
        ),
        # MX record — exercises the renamed `mx_host` / `mx_priority` args
        # (were `mx` / `mxprio`).
        ResourceConfig(
            provider="opnsense",
            type="unbound_host_override",
            name="uho-mx",
            config={
                "hostname": "mail",
                "domain": "example.com",
                "rr": "MX",
                "mx": "mail.example.com",
                "mxprio": "10",
            },
        ),
    ]


# Maps `(template_label, output_filename)` to the fixture-builder.
#
# `dhcp_static_maps` is INTENTIONALLY EXCLUDED (#765). The template references
# `opnsense_dhcpv4_static_map`, which doesn't exist in the current
# `browningluke/opnsense` provider. Resolution — delete the template or port
# to `opnsense_kea_reservation` — is its own decision and is tracked as a
# follow-up to #765.
# TODO(#765 follow-up): Resolve `dhcp_static_maps.tf.j2` and re-include here.
_TEMPLATE_PARAMS: list[tuple[str, str, Any]] = [
    ("kea_subnet", "kea_subnet.tf", _kea_subnet_resources),
    ("kea_reservation", "kea_reservation.tf", _kea_reservation_resources),
    (
        "unbound_host_override",
        "unbound_host_overrides.tf",
        _unbound_host_override_resources,
    ),
]


@pytest.fixture
def schema() -> dict[str, set[str]]:
    """Loaded provider schema fixture."""
    return _load_schema()


@pytest.fixture
def provider(tmp_path: Path) -> OPNsenseProvider:
    """OPNsense provider rooted in a per-test tmp dir."""
    config_dir = tmp_path / "config"
    output_dir = tmp_path / "output"
    return OPNsenseProvider(config_dir, output_dir)


@pytest.mark.parametrize(
    ("template_label", "output_filename", "fixture_factory"),
    _TEMPLATE_PARAMS,
    ids=[label for label, _, _ in _TEMPLATE_PARAMS],
)
def test_rendered_arguments_are_in_provider_schema(
    template_label: str,
    output_filename: str,
    fixture_factory: Any,
    provider: OPNsenseProvider,
    schema: dict[str, set[str]],
) -> None:
    """Render the template, extract argument names per resource block, and
    assert every name is in the schema fixture for that resource type.
    """
    del template_label  # used only for the parametrize id
    resources = fixture_factory()
    provider.generate_terraform(resources)

    rendered = (provider.terraform_dir / output_filename).read_text()
    blocks = _extract_resource_blocks(rendered)

    assert blocks, (
        f"Template {output_filename!r} rendered no resource blocks — "
        f"the test fixture must produce at least one resource."
    )

    for resource_type, body in blocks:
        assert resource_type in schema, (
            f"Resource type {resource_type!r} rendered by {output_filename} "
            f"is not in the provider schema fixture. Either the template "
            f"references a nonexistent resource type, or the schema fixture "
            f"needs regeneration (see fixtures/README.md)."
        )
        rendered_args = set(_HCL_ARG_RE.findall(body))
        unsupported = rendered_args - schema[resource_type]
        assert not unsupported, (
            f"Template {output_filename} renders argument(s) "
            f"{sorted(unsupported)!r} on resource {resource_type!r} that are "
            f"not in the provider schema. Either the template uses the wrong "
            f"argument name, or the schema fixture needs regeneration "
            f"(see fixtures/README.md)."
        )
