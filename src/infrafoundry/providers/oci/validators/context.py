"""Validation context for the OCI sub-validators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationContext


@dataclass(frozen=True, kw_only=True)
class OCIApiContext(ValidationContext):
    """Context carrying pre-fetched OCI API data.

    A list field is ``None`` when the API call that fills it failed or was not made.

    Attributes:
        compartment_ocid: The compartment OCID from provider settings.
        compartments: Compartment dicts from the OCI API.
        existing_vcns: VCN dicts from the OCI API.
        existing_subnets: Subnet dicts from the OCI API.
        existing_images: Image dicts from the OCI API.
        region: The region from provider settings.
        region_subscriptions: Region subscription dicts for the tenancy.
    """

    compartment_ocid: str
    compartments: list[dict[str, Any]] | None = None
    existing_vcns: list[dict[str, Any]] | None = None
    existing_subnets: list[dict[str, Any]] | None = None
    existing_images: list[dict[str, Any]] | None = None
    region: str = ""
    region_subscriptions: list[dict[str, Any]] | None = None


@dataclass(frozen=True, kw_only=True)
class OCIStorageIamContext(ValidationContext):
    """Context for the offline bucket and IAM checks.

    Attributes:
        reference_resources: Every OCI resource in the environment, used to resolve
            names when ``resources`` is a filtered subset.
    """

    reference_resources: list[ResourceConfig] = field(default_factory=list)
