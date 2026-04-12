"""Unit tests for blueprint extra_tags support.

Verifies that Jinja2 tag expressions in blueprint resource templates correctly
merge hardcoded tags with the extra_tags variable.
"""

from pathlib import Path

import jinja2
import pytest
import yaml

# Root of the blueprints directory
BLUEPRINTS_DIR = Path(__file__).resolve().parents[2] / "blueprints"

# Tag expressions used in each blueprint, mapped to their resource files.
# Each entry: (blueprint, resource_file, base_tags_list)
BLUEPRINT_TAG_CASES = [
    ("aiqum", "vm.yaml", ["ontap", "aiqum"]),
    ("proxmox-k3s-cluster", "vm.yaml", ["k3s", "k3s-server"]),
    ("proxmox-k3s-cluster", "vm.yaml", ["k3s", "k3s-agent"]),
    ("ontap-cluster", "vm.yaml", ["ontap", "ontap-lab"]),
    ("rocky9-template", "template.yaml", ["template", "rocky9"]),
    ("ubuntu-template", "template.yaml", ["template", "ubuntu"]),
]


def _render_tag_expression(base_tags: list[str], extra_tags: list[str]) -> list[str]:
    """Render a Jinja2 tag concatenation expression and parse the result as YAML.

    Simulates the rendering pipeline used by PackageLoader._render_resource_file.

    Args:
        base_tags: The hardcoded tag list (e.g. ["ontap", "aiqum"]).
        extra_tags: The user-supplied extra tags list.

    Returns:
        The merged list of tags after Jinja2 rendering and YAML parsing.
    """
    template_str = "tags: {{ base + extra }}"
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    template = env.from_string(template_str)
    rendered = template.render(base=base_tags, extra=extra_tags)
    data = yaml.safe_load(rendered)
    return data["tags"]


@pytest.mark.unit
class TestExtraTagsExpression:
    """Test that Jinja2 list concatenation produces correct tag lists."""

    def test_empty_extra_tags_preserves_base(self):
        """Default extra_tags=[] produces only the base tags."""
        result = _render_tag_expression(["ontap", "aiqum"], [])
        assert result == ["ontap", "aiqum"]

    def test_single_extra_tag_appended(self):
        """A single extra tag is appended after the base tags."""
        result = _render_tag_expression(["ontap", "aiqum"], ["test"])
        assert result == ["ontap", "aiqum", "test"]

    def test_multiple_extra_tags_appended(self):
        """Multiple extra tags are appended in order."""
        result = _render_tag_expression(["ontap", "aiqum"], ["test", "dev"])
        assert result == ["ontap", "aiqum", "test", "dev"]

    @pytest.mark.parametrize(
        "base_tags",
        [
            ["ontap", "aiqum"],
            ["k3s", "k3s-server"],
            ["k3s", "k3s-agent"],
            ["ontap", "ontap-lab"],
            ["template", "rocky9"],
            ["template", "ubuntu"],
        ],
        ids=[
            "aiqum",
            "k3s-server",
            "k3s-agent",
            "ontap-cluster",
            "rocky9-template",
            "ubuntu-template",
        ],
    )
    def test_all_blueprints_empty_extra(self, base_tags):
        """Each blueprint's base tags are preserved when extra_tags is empty."""
        result = _render_tag_expression(base_tags, [])
        assert result == base_tags

    @pytest.mark.parametrize(
        "base_tags",
        [
            ["ontap", "aiqum"],
            ["k3s", "k3s-server"],
            ["k3s", "k3s-agent"],
            ["ontap", "ontap-lab"],
            ["template", "rocky9"],
            ["template", "ubuntu"],
        ],
        ids=[
            "aiqum",
            "k3s-server",
            "k3s-agent",
            "ontap-cluster",
            "rocky9-template",
            "ubuntu-template",
        ],
    )
    def test_all_blueprints_with_extra(self, base_tags):
        """Each blueprint's base tags are extended when extra_tags is non-empty."""
        result = _render_tag_expression(base_tags, ["custom", "env-test"])
        assert result == [*base_tags, "custom", "env-test"]


@pytest.mark.unit
class TestBlueprintDefaultsIncludeExtraTags:
    """Verify that each blueprint.yaml declares extra_tags in its defaults."""

    @pytest.mark.parametrize(
        "blueprint",
        [
            "aiqum",
            "proxmox-k3s-cluster",
            "ontap-cluster",
            "rocky9-template",
            "ubuntu-template",
        ],
    )
    def test_extra_tags_in_defaults(self, blueprint):
        """Blueprint defaults must include extra_tags with an empty list default."""
        blueprint_path = BLUEPRINTS_DIR / blueprint / "blueprint.yaml"
        data = yaml.safe_load(blueprint_path.read_text())
        assert "extra_tags" in data["defaults"], (
            f"{blueprint}/blueprint.yaml missing extra_tags in defaults"
        )
        assert data["defaults"]["extra_tags"] == []


@pytest.mark.unit
class TestResourceTemplatesUseExtraTags:
    """Verify that resource templates reference extra_tags in their tag expressions."""

    @pytest.mark.parametrize(
        "blueprint,resource_file",
        [
            ("aiqum", "vm.yaml"),
            ("proxmox-k3s-cluster", "vm.yaml"),
            ("ontap-cluster", "vm.yaml"),
            ("rocky9-template", "template.yaml"),
            ("ubuntu-template", "template.yaml"),
        ],
    )
    def test_template_contains_extra_tags(self, blueprint, resource_file):
        """Resource template must contain '+ extra_tags' in a tags expression."""
        resource_path = BLUEPRINTS_DIR / blueprint / resource_file
        content = resource_path.read_text()
        assert "+ extra_tags" in content, (
            f"{blueprint}/{resource_file} does not reference extra_tags in tags expression"
        )
