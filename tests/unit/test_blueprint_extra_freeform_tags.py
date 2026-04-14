"""Unit tests for OCI blueprint extra_freeform_tags support.

Verifies that Jinja2 freeform_tags blocks in the OCI k3s blueprint correctly
merge hardcoded tags with the extra_freeform_tags variable.
"""

from pathlib import Path

import jinja2
import pytest
import yaml

# Root of the blueprints directory
BLUEPRINTS_DIR = Path(__file__).resolve().parents[2] / "blueprints"

# Minimal template that mirrors the freeform_tags block in instance.yaml
FREEFORM_TAGS_TEMPLATE = """\
freeform_tags:
  role: control-plane
  cluster: "{{ cluster_name }}"
  managed_by: infrafoundry
{% for key, value in extra_freeform_tags.items() %}
  {{ key }}: "{{ value }}"
{% endfor %}"""


def _render_freeform_tags(
    extra_freeform_tags: dict[str, str],
    cluster_name: str = "test-cluster",
) -> dict[str, str]:
    """Render a freeform_tags template block and return the parsed dict.

    Args:
        extra_freeform_tags: Additional freeform tags to merge.
        cluster_name: Cluster name for the template context.

    Returns:
        The freeform_tags dict after Jinja2 rendering and YAML parsing.
    """
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    template = env.from_string(FREEFORM_TAGS_TEMPLATE)
    rendered = template.render(
        cluster_name=cluster_name,
        extra_freeform_tags=extra_freeform_tags,
    )
    data = yaml.safe_load(rendered)
    return data["freeform_tags"]


@pytest.mark.unit
class TestExtraFreeformTagsExpression:
    """Test that Jinja2 dict iteration produces correct freeform_tags."""

    def test_empty_extra_freeform_tags_preserves_base(self):
        """Default extra_freeform_tags={} produces only the hardcoded tags."""
        result = _render_freeform_tags({})
        assert result == {
            "role": "control-plane",
            "cluster": "test-cluster",
            "managed_by": "infrafoundry",
        }

    def test_single_extra_freeform_tag_added(self):
        """A single extra freeform tag is included in the output."""
        result = _render_freeform_tags({"environment": "test"})
        assert result["environment"] == "test"
        assert result["role"] == "control-plane"
        assert result["cluster"] == "test-cluster"
        assert result["managed_by"] == "infrafoundry"

    def test_multiple_extra_freeform_tags_added(self):
        """Multiple extra freeform tags are all included."""
        result = _render_freeform_tags({"environment": "test", "team": "platform"})
        assert result["environment"] == "test"
        assert result["team"] == "platform"
        assert result["role"] == "control-plane"
        assert result["cluster"] == "test-cluster"
        assert result["managed_by"] == "infrafoundry"
        assert len(result) == 5


@pytest.mark.unit
class TestBlueprintDefaultsIncludeExtraFreeformTags:
    """Verify that oci-k3s-cluster blueprint.yaml declares extra_freeform_tags."""

    def test_extra_freeform_tags_in_defaults(self):
        """Blueprint inputs must declare extra_freeform_tags with an empty dict default."""
        blueprint_path = BLUEPRINTS_DIR / "k3s-cluster" / "blueprint.yaml"
        data = yaml.safe_load(blueprint_path.read_text())
        # Multi-provider blueprint: extra_freeform_tags is under providers.oci.inputs
        inputs = data["providers"]["oci"]["inputs"]
        by_name = {entry["name"]: entry for entry in inputs if "name" in entry}
        assert "extra_freeform_tags" in by_name, (
            "k3s-cluster/blueprint.yaml missing extra_freeform_tags input declaration"
        )
        assert by_name["extra_freeform_tags"].get("default") == {}


@pytest.mark.unit
class TestResourceTemplatesUseExtraFreeformTags:
    """Verify that instance.yaml references extra_freeform_tags."""

    def test_template_contains_extra_freeform_tags(self):
        """Resource template must contain 'extra_freeform_tags' in a loop."""
        resource_path = BLUEPRINTS_DIR / "k3s-cluster" / "providers" / "oci" / "instance.yaml"
        content = resource_path.read_text()
        assert "extra_freeform_tags" in content, (
            "k3s-cluster/providers/oci/instance.yaml does not reference extra_freeform_tags"
        )
