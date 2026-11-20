"""Offline validation of OCI buckets and IAM resources."""

from __future__ import annotations

import re
from typing import override

from infrafoundry.core.protocols import SpecializedValidator
from infrafoundry.core.provider import ResourceConfig
from infrafoundry.core.validation import ValidationLevel, ValidationReport
from infrafoundry.providers.oci.compartments import is_ocid
from infrafoundry.providers.oci.validators.context import OCIStorageIamContext

STORAGE_TIERS = ("Standard", "Archive")
VERSIONING = ("Enabled", "Disabled")
ACCESS_TYPES = ("NoPublicAccess", "ObjectRead", "ObjectReadWithoutList")
LIFECYCLE_ACTIONS = ("DELETE", "ARCHIVE", "INFREQUENT_ACCESS", "ABORT")
LIFECYCLE_UNITS = ("DAYS", "YEARS")

_OUTPUT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_TENANCY_TYPES = ("iam_user", "iam_group", "customer_secret_key")


class StorageIamValidator(SpecializedValidator[OCIStorageIamContext]):
    """Checks bucket settings, lifecycle rules and IAM references without any API call."""

    def __init__(self, report: ValidationReport) -> None:
        """Initialize the validator.

        Args:
            report: ValidationReport to add results to.
        """
        self.report = report

    def _add(self, check: str, message: str, level: ValidationLevel) -> None:
        self.report.add_check(check_name=check, passed=False, message=message, level=level)

    def _error(self, check: str, message: str) -> None:
        self._add(check, message, ValidationLevel.ERROR)

    @override
    def validate(self, context: OCIStorageIamContext) -> None:
        """Validate bucket and IAM resources.

        Args:
            context: The resources to check and every OCI resource in the environment,
                used to resolve names when the resources are a filtered subset.
        """
        resources = context.resources
        pool = [*context.reference_resources, *resources]
        users = {r.name for r in pool if r.type == "iam_user"}
        compartments = {r.name for r in pool if r.type == "compartment"}
        for res in resources:
            if res.type == "bucket":
                self._bucket(res)
            elif res.type == "iam_user":
                self._user(res)
            elif res.type == "iam_group":
                self._group(res, users)
            elif res.type == "iam_policy":
                self._policy(res, compartments)
            elif res.type == "customer_secret_key":
                self._key(res, users)
            if res.type in _TENANCY_TYPES and res.config.get("compartment"):
                self._add(
                    f"oci_{res.type}_{res.name}_compartment",
                    f"{res.type} '{res.name}' sets a compartment, which is ignored: "
                    f"IAM objects live in the tenancy",
                    ValidationLevel.WARNING,
                )

    def _enum(self, res: ResourceConfig, field: str, allowed: tuple[str, ...]) -> None:
        value = res.config.get(field)
        if value is not None and value not in allowed:
            self._error(
                f"oci_bucket_{res.name}_{field}",
                f"Bucket '{res.name}' has {field} '{value}'; allowed: {', '.join(allowed)}",
            )

    def _bucket(self, res: ResourceConfig) -> None:
        self._enum(res, "storage_tier", STORAGE_TIERS)
        self._enum(res, "versioning", VERSIONING)
        self._enum(res, "access_type", ACCESS_TYPES)
        rules = res.config.get("lifecycle")
        if rules is None:
            return
        if not isinstance(rules, list):
            self._error(
                f"oci_bucket_{res.name}_lifecycle", f"Bucket '{res.name}': lifecycle must be a list"
            )
            return
        seen: set[str] = set()
        for index, rule in enumerate(rules):
            check = f"oci_bucket_{res.name}_lifecycle_{index}"
            if not isinstance(rule, dict):
                self._error(check, f"Bucket '{res.name}': lifecycle rule {index} must be a mapping")
                continue
            self._rule(res.name, check, rule, seen)

    def _rule(self, bucket: str, check: str, rule: dict[str, object], seen: set[str]) -> None:
        name = rule.get("name")
        if not isinstance(name, str) or not name:
            self._error(f"{check}_name", f"Bucket '{bucket}': a lifecycle rule requires a name")
        elif name in seen:
            self._error(f"{check}_name", f"Bucket '{bucket}': duplicate lifecycle rule '{name}'")
        else:
            seen.add(name)
        if rule.get("action") not in LIFECYCLE_ACTIONS:
            self._error(
                f"{check}_action",
                f"Bucket '{bucket}': lifecycle action '{rule.get('action')}'; "
                f"allowed: {', '.join(LIFECYCLE_ACTIONS)}",
            )
        amount = rule.get("time_amount")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            self._error(
                f"{check}_time_amount",
                f"Bucket '{bucket}': lifecycle time_amount must be a positive integer",
            )
        if rule.get("time_unit") not in LIFECYCLE_UNITS:
            self._error(
                f"{check}_time_unit",
                f"Bucket '{bucket}': lifecycle time_unit '{rule.get('time_unit')}'; "
                f"allowed: {', '.join(LIFECYCLE_UNITS)}",
            )

    def _user(self, res: ResourceConfig) -> None:
        if "email" not in res.config:
            return
        email = res.config["email"]
        if not isinstance(email, str) or not email.strip() or "@" not in email:
            self._error(
                f"oci_iam_user_{res.name}_email",
                f"User '{res.name}' email must be a non-empty string containing '@'",
            )

    def _group(self, res: ResourceConfig, users: set[str]) -> None:
        for member in res.config.get("members") or []:
            if member not in users:
                self._error(
                    f"oci_iam_group_{res.name}_member_{member}",
                    f"Group '{res.name}' lists member '{member}' which is not a defined iam_user",
                )

    def _policy(self, res: ResourceConfig, compartments: set[str]) -> None:
        statements = res.config.get("statements")
        if (
            not isinstance(statements, list)
            or not statements
            or not all(isinstance(s, str) and s for s in statements)
        ):
            self._error(
                f"oci_iam_policy_{res.name}_statements",
                f"Policy '{res.name}' requires a non-empty list of statement strings",
            )
        ref = res.config.get("compartment")
        if ref and not is_ocid(str(ref)) and ref not in compartments:
            self._error(
                f"oci_iam_policy_{res.name}_compartment",
                f"Policy '{res.name}' references compartment '{ref}' which is neither "
                f"an OCID nor a defined compartment",
            )

    def _key(self, res: ResourceConfig, users: set[str]) -> None:
        user = res.config.get("user")
        if not user or user not in users:
            self._error(
                f"oci_customer_secret_key_{res.name}_user",
                f"Customer secret key '{res.name}' references user '{user}' which is not "
                f"a defined iam_user",
            )
        if not _OUTPUT_NAME.match(res.name.replace("-", "_")):
            self._add(
                f"oci_customer_secret_key_{res.name}_name",
                f"Customer secret key '{res.name}' cannot be referenced as "
                f"outputs.oci.customer_secret_key_<name>_secret: its output name must match "
                f"{_OUTPUT_NAME.pattern}",
                ValidationLevel.WARNING,
            )
