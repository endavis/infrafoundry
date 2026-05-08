"""Parameterized regression tests asserting that every terraform argument
emitted by an OPNsense `*.tf.j2` template is a supported attribute of the
target `browningluke/opnsense` resource type.

After #782, every OPNsense component is managed by ``OPNsenseDirectRunner``
— no terraform write paths remain — so ``_TEMPLATE_PARAMS`` is empty and
the parametrize collects zero cases. The harness is retained so a future
terraform-managed component (if any is added) can be wired in by appending
to the list. The schema fixture is a pinned snapshot of the provider's
``terraform providers schema -json`` output; see
``tests/unit/providers/opnsense/fixtures/README.md`` for regeneration
instructions.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

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


# Maps `(template_label, output_filename, fixture_factory)` for templates
# that are still terraform-managed and within scope of this compliance
# regression. After the cutover-unblock series (#775 firewall_alias, #776
# unbound_host_override, #758 kea_dhcp6, #777/#778 kea_subnet/kea_reservation
# DHCPv4) and the dhcp_static_maps retirement (#782), this list is empty.
# Add a new entry only if a future OPNsense component reverts to or
# introduces a terraform write path.
_TEMPLATE_PARAMS: list[tuple[str, str, Any]] = []


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
