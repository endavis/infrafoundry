"""Image validation for OCI provider."""

from __future__ import annotations

from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport


class ImageValidator:
    """Validates that image OCIDs referenced by instances exist in OCI.

    This is a report-only validator that works with pre-fetched image data.
    The main OCI validator handles API authentication and data fetching.
    """

    def __init__(self, report: ValidationReport) -> None:
        """Initialize image validator.

        Args:
            report: ValidationReport to add results to
        """
        self.report = report

    def validate(
        self,
        resources: list[ResourceConfig],
        existing_images: list[dict[str, Any]] | None,
    ) -> None:
        """Validate that image OCIDs referenced by instances exist.

        Args:
            resources: List of resources from the configuration
            existing_images: Pre-fetched image list from OCI API, or None if unavailable
        """
        if existing_images is None:
            return

        instances = [r for r in resources if r.type == "instance"]
        if not instances:
            return

        image_map = {img.get("id", ""): img.get("displayName", "") for img in existing_images}

        # Collect unique image OCIDs and the instances that reference them
        image_refs: dict[str, list[str]] = {}
        for instance in instances:
            image_ocid = instance.config.get("image_ocid", "")
            if image_ocid:
                if image_ocid not in image_refs:
                    image_refs[image_ocid] = []
                image_refs[image_ocid].append(instance.name)

        for image_ocid, instance_names in sorted(image_refs.items()):
            if image_ocid in image_map:
                display_name = image_map[image_ocid]
                self.report.add_check(
                    check_name=f"oci_image_{image_ocid[:20]}",
                    passed=True,
                    message=(
                        f"Image '{display_name}' ({image_ocid}) exists "
                        f"(used by: {', '.join(instance_names)})"
                    ),
                )
            else:
                self.report.add_check(
                    check_name=f"oci_image_{image_ocid[:20]}",
                    passed=False,
                    message=(
                        f"Image '{image_ocid}' not found in compartment "
                        f"(referenced by: {', '.join(instance_names)})"
                    ),
                    level=ValidationLevel.ERROR,
                )
