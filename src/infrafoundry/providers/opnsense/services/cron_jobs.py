"""Cron-jobs service for OPNsense direct-API operations (#789).

Manages OPNsense scheduled tasks via the ``cron/settings/`` MVC controller.
Each job is a distinct UUID-keyed record on the box.

Identity strategy
-----------------

Cron jobs have no clean intrinsic key — two jobs can share the same
``command`` on different schedules. This service uses the description-suffix
identity scheme mirrored from ``nat_rules`` and ``firewall_rules``:
``description`` carries an ``<operator description> [infrafoundry:<name>]``
suffix tag. Live jobs without the suffix tag are unmanaged and silently
ignored by the diff.

Wire-operator field mapping
---------------------------

The operator authors a YAML cron job with snake_case names that map 1:1 to
the OPNsense wire schema:

- ``enabled``     → ``enabled``     (``"0"``/``"1"``)
- ``minutes``     → ``minutes``     (``"*"``, ``"0"``, etc.)
- ``hours``       → ``hours``
- ``days``        → ``days``        (1:1 pass-through; wire key is ``days``)
- ``months``      → ``months``      (1:1 pass-through; wire key is ``months``)
- ``weekdays``    → ``weekdays``    (1:1 pass-through; wire key is ``weekdays``)
- ``who``         → ``who``         (user to run as, e.g. ``"root"``)
- ``command``     → ``command``
- ``parameters``  → ``parameters``
- ``description`` → ``description`` (identity suffix appended at serialization)
- ``origin``      → ``origin``      (REQUIRED wire field; InfraFoundry always
  writes ``"cron"`` so that ``delJob`` can delete managed jobs — OPNsense's
  ``delJob`` endpoint is delete-protected for non-``"cron"`` origins)

``lock`` and ``name`` are InfraFoundry metadata, not sent on the wire.

Finalization hook
-----------------

The component manager declares ``FINALIZATION_HOOK = "cron_reconfigure"``.
The runner fires this hook once after all cron jobs have been applied.
This service's :meth:`reconfigure` method exists for the hook to call;
the manager itself MUST NOT call reconfigure directly.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.exceptions import InfraFoundryError
from infrafoundry.core.provider import ResourceConfig

from ..api_client import CronClient, OPNsenseClient
from ._nested_emit import emit_nested_list_yaml
from .base import BaseService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Identity helpers (duplicated from firewall_rule.py — do NOT refactor)
# ---------------------------------------------------------------------------

# Regex for parsing the description-suffix identity tag. Operator-supplied
# free-form text leads, followed by whitespace, followed by
# ``\[infrafoundry:<name>\]`` at the end of the string.
_IDENTITY_PATTERN = re.compile(r"^(?:(.+?)\s+)?\[infrafoundry:([a-z0-9-]+)\]\s*$")
_IDENTITY_PROBE = re.compile(r"\[infrafoundry:[^\]]*\]")


class OpnsenseDriftError(InfraFoundryError):
    """A managed cron job's identity tag is malformed on the live box.

    Raised by the diff engine when a live job's ``description`` looks
    like it carries an InfraFoundry tag but does not match the strict
    identity regex. The operator must repair the description in the GUI
    (or via API) before the next plan/apply.
    """


def encode_identity(resource_name: str, user_description: str) -> str:
    """Encode the description with the InfraFoundry identity suffix.

    Args:
        resource_name: Operator-facing YAML name; becomes the diff key.
        user_description: Free-form description from YAML (may be empty).

    Returns:
        ``"<user_description> [infrafoundry:<name>]"`` when the user
        description is non-empty; ``"[infrafoundry:<name>]"`` otherwise.
    """
    if user_description:
        return f"{user_description} [infrafoundry:{resource_name}]"
    return f"[infrafoundry:{resource_name}]"


def parse_identity(description: str) -> tuple[str | None, str]:
    """Parse the description-suffix identity tag.

    Args:
        description: ``description`` field from a live job row.

    Returns:
        ``(resource_name, user_description)``. ``resource_name`` is
        ``None`` when the description has no tag (unmanaged job).

    Raises:
        OpnsenseDriftError: If the description contains the
            ``[infrafoundry:...]`` marker but does not match the strict
            suffix-only regex.
    """
    match = _IDENTITY_PATTERN.match(description)
    if match is not None:
        user_desc = match.group(1) or ""
        return match.group(2), user_desc
    if _IDENTITY_PROBE.search(description):
        raise OpnsenseDriftError(
            f"Cron job description contains an InfraFoundry identity tag but is malformed: "
            f"{description!r}. Expected '<user description> [infrafoundry:<name>]' (or just "
            f"'[infrafoundry:<name>]') where <name> matches [a-z0-9-]+ (non-empty) and the "
            f"tag is the LAST token in the description."
        )
    return None, description


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CronJobConfig:
    """Desired-state cron job configuration.

    Attributes:
        name: Operator-facing YAML name; becomes the diff key.
        enabled: Whether the job is active.
        minutes: Cron minute field (e.g. ``"0"``, ``"*/5"``).
        hours: Cron hour field.
        days: Cron day-of-month field. Wire key is ``days`` (1:1 pass-through).
        months: Cron month field. Wire key is ``months`` (1:1 pass-through).
        weekdays: Cron day-of-week field. Wire key is ``weekdays`` (1:1 pass-through).
        who: User to run the job as (e.g. ``"root"``).
        command: Command to execute.
        parameters: Optional command parameters.
        description: Free-form description (no identity suffix in YAML;
            added automatically at serialization time).
        origin: Origin label from the operator YAML (e.g. ``"AcmeClient"``).
            InfraFoundry ALWAYS writes ``"cron"`` on the wire regardless of
            this value — ``delJob`` is delete-protected for non-``"cron"``
            origins.  Excluded from drift detection to avoid perpetual updates
            when the operator sets a non-default origin in YAML.
        lock: Per-resource safety annotation (ADR-0014 §6). When True,
            the diff engine and destroy path skip this resource.
    """

    name: str
    enabled: bool = True
    minutes: str = "*"
    hours: str = "*"
    days: str = "*"
    months: str = "*"
    weekdays: str = "*"
    who: str = "root"
    command: str = ""
    parameters: str = ""
    description: str = ""
    origin: str = "cron"
    lock: bool = False

    def encoded_description(self) -> str:
        """Description with the InfraFoundry identity suffix applied."""
        return encode_identity(self.name, self.description)

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``addJob``/``setJob`` envelope OPNsense expects.

        Returns:
            ``{"job": {<wire-keyed fields>}}``. ``enabled`` serializes to
            ``"0"``/``"1"``; the ``description`` field carries the identity
            suffix tag; the ``lock`` and ``name`` meta-fields are omitted.
        """
        return {
            "job": {
                "enabled": "1" if self.enabled else "0",
                "minutes": self.minutes,
                "hours": self.hours,
                "days": self.days,
                "months": self.months,
                "weekdays": self.weekdays,
                "who": self.who,
                "command": self.command,
                "parameters": self.parameters,
                "description": self.encoded_description(),
                # origin is a REQUIRED wire field; always force "cron" so that
                # delJob can delete this job.  Non-"cron" origins are
                # delete-protected by OPNsense (verified by live probe 2026-06-18).
                "origin": "cron",
            }
        }


@dataclass(frozen=True)
class LiveCronJob:
    """A cron job as currently configured on the OPNsense box.

    Identity-tagged jobs have ``managed_name`` set to the parsed
    resource name; unmanaged jobs have it set to ``None`` and are
    filtered out of the diff entirely.

    Attributes:
        uuid: OPNsense-assigned job UUID.
        managed_name: Parsed InfraFoundry name (``None`` if unmanaged).
        description: Free-form description with the identity suffix stripped.
        origin: Origin label from the live record.
        raw: Full original row dict from ``searchJobs`` for field
            comparison during update detection.
    """

    uuid: str
    managed_name: str | None
    description: str
    origin: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Diff:
    """Result of comparing desired YAML state to live OPNsense state.

    Attributes:
        adds: Jobs to create (in desired but not on box).
        updates: Jobs to update ``(live, desired)`` tuples.
        deletes: Managed jobs on the box that are absent from desired.
        locked: Resources skipped due to ``lock: true``.
    """

    adds: list[CronJobConfig] = field(default_factory=list)
    updates: list[tuple[LiveCronJob, CronJobConfig]] = field(default_factory=list)
    deletes: list[LiveCronJob] = field(default_factory=list)
    locked: list[tuple[CronJobConfig, LiveCronJob | None]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there are no add/update/delete operations to apply."""
        return not (self.adds or self.updates or self.deletes)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def compute_diff(
    desired: list[CronJobConfig],
    current: list[LiveCronJob],
    *,
    add_only: bool = False,
) -> Diff:
    """Compare desired YAML state to live state.

    Unmanaged live jobs (``managed_name is None``) are silently ignored:
    not deleted, not updated, never reported.

    Args:
        desired: Cron jobs the operator wants to exist.
        current: Cron jobs currently on the box.
        add_only: If True, never emit deletes for managed live jobs
            that don't appear in ``desired``. Adds and updates still
            happen.

    Returns:
        ``Diff`` with adds/updates/deletes plus locked entries.
    """
    desired_by_name: dict[str, CronJobConfig] = {d.name: d for d in desired}
    current_managed: dict[str, LiveCronJob] = {
        live.managed_name: live for live in current if live.managed_name is not None
    }
    locked_names: set[str] = {d.name for d in desired if d.lock}

    adds: list[CronJobConfig] = []
    updates: list[tuple[LiveCronJob, CronJobConfig]] = []
    deletes: list[LiveCronJob] = []
    locked: list[tuple[CronJobConfig, LiveCronJob | None]] = []

    for name, want in desired_by_name.items():
        have = current_managed.get(name)
        if want.lock:
            locked.append((want, have))
            continue
        if have is None:
            adds.append(want)
        elif _needs_update(have, want):
            updates.append((have, want))

    if not add_only:
        for name, have in current_managed.items():
            if name in locked_names:
                continue
            if name not in desired_by_name:
                deletes.append(have)

    return Diff(adds=adds, updates=updates, deletes=deletes, locked=locked)


def _needs_update(have: LiveCronJob, want: CronJobConfig) -> bool:
    """Return True if the live row's fields differ from the desired payload.

    Compares the payload fields we write against the live raw row.

    Args:
        have: Live cron job record.
        want: Desired configuration.

    Returns:
        True if any comparable field differs.
    """
    payload = want.to_payload()["job"]
    for wire_key, want_value in payload.items():
        # origin is always forced to "cron" on write (see to_payload) but the
        # live record may carry a plugin origin (e.g. "AcmeClient").  Comparing
        # origin would cause perpetual spurious updates for YAML jobs whose
        # operator-supplied origin differs from the live record's origin.
        if wire_key == "origin":
            continue
        have_value = _normalize_field(have.raw.get(wire_key))
        if str(want_value) != have_value:
            return True
    return False


def _normalize_field(value: Any) -> str:
    """Collapse an OPNsense field value to a comparable string.

    OPNsense returns single-select fields as dicts of options keyed by
    their machine value; the active option has ``"selected": 1``. We
    extract that option and return its key (matching what we'd send on
    update). Empty/None values become ``""``. Plain scalars are
    stringified verbatim.

    Args:
        value: Raw field value from a live record row.

    Returns:
        Normalized string for comparison.
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        for option_key, option_value in value.items():
            if isinstance(option_value, dict) and option_value.get("selected"):
                return str(option_key)
        return ""
    return str(value)


def plugin_conflicts(
    desired: list[CronJobConfig],
    live: list[LiveCronJob],
) -> list[tuple[CronJobConfig, LiveCronJob]]:
    """Detect plan-time WARNING conflicts: unmanaged live jobs sharing a command.

    An unmanaged live job that shares a ``command`` with a managed YAML
    job is a potential conflict. The caller (manager's ``plan`` method)
    logs a WARNING for each conflict and continues — this is advisory,
    not an error.

    Args:
        desired: Desired-state cron jobs from YAML.
        live: Live cron jobs currently on the box.

    Returns:
        List of ``(desired_job, conflicting_live_job)`` pairs. Empty when
        no conflicts exist.
    """
    desired_commands = {d.command: d for d in desired if d.command}
    conflicts: list[tuple[CronJobConfig, LiveCronJob]] = []
    for live_job in live:
        if live_job.managed_name is not None:
            continue  # managed; handled by the diff engine
        if live_job.raw.get("command") and live_job.raw["command"] in desired_commands:
            conflicts.append((desired_commands[live_job.raw["command"]], live_job))
    return conflicts


# ---------------------------------------------------------------------------
# Resource-to-domain conversion
# ---------------------------------------------------------------------------


def cron_job_configs_from_resources(
    resources: list[ResourceConfig],
) -> list[CronJobConfig]:
    """Convert ``ResourceConfig`` entries to ``CronJobConfig`` instances.

    Args:
        resources: All provider resources from a ConfigManager load.
            Non-``cron.jobs`` entries are silently skipped.

    Returns:
        Validated ``CronJobConfig`` list.

    Raises:
        ValueError: If an entry has a non-dict config, missing/invalid
            required fields, or a forged identity prefix in ``description``.
    """
    configs: list[CronJobConfig] = []
    for resource in resources:
        if resource.type != "cron.jobs":
            continue
        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"cron_job '{resource.name}' has non-dict config")
        configs.append(_build_config(resource.name, config))
    return configs


def _build_config(name: str, config: dict[str, Any]) -> CronJobConfig:
    """Build a single ``CronJobConfig`` from a YAML config dict.

    Args:
        name: Operator-facing YAML resource name.
        config: Raw config dict from the YAML resource.

    Returns:
        Validated ``CronJobConfig``.

    Raises:
        ValueError: On invalid field types or reserved description content.
    """
    description = config.get("description", "")
    if not isinstance(description, str):
        raise ValueError(f"cron_job '{name}' description must be a string")
    if _IDENTITY_PROBE.search(description):
        raise ValueError(
            f"cron_job '{name}' description must not contain "
            f"'[infrafoundry:<name>]' — that tag is reserved for InfraFoundry's "
            f"identity suffix, which is added automatically at apply time"
        )

    enabled_raw = config.get("enabled", True)
    if not isinstance(enabled_raw, bool):
        raise ValueError(
            f"cron_job '{name}' enabled must be a boolean (true/false), "
            f"got {type(enabled_raw).__name__}"
        )
    lock_raw = config.get("lock", False)
    if not isinstance(lock_raw, bool):
        raise ValueError(
            f"cron_job '{name}' lock must be a boolean (true/false), got {type(lock_raw).__name__}"
        )

    def _str_field(field_name: str, default: str = "*") -> str:
        value = config.get(field_name, default)
        if not isinstance(value, str):
            raise ValueError(
                f"cron_job '{name}' {field_name} must be a string, got {type(value).__name__}"
            )
        return value

    return CronJobConfig(
        name=name,
        enabled=enabled_raw,
        minutes=_str_field("minutes"),
        hours=_str_field("hours"),
        days=_str_field("days"),
        months=_str_field("months"),
        weekdays=_str_field("weekdays"),
        who=_str_field("who", default="root"),
        command=_str_field("command", default=""),
        parameters=_str_field("parameters", default=""),
        description=description,
        origin=_str_field("origin", default=""),
        lock=lock_raw,
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class CronJobsService(BaseService):
    """Service for OPNsense cron-job operations via direct API.

    Uses the ``cron/settings/`` MVC controller. Each cron job is a
    UUID-keyed record; identity is description-suffix-based.
    """

    def __init__(self, client: OPNsenseClient) -> None:
        """Initialize the service with a CronClient wrapper."""
        super().__init__(client)
        self._cron = CronClient(client)

    # ------------------------------------------------------------------
    # API operations (CRUD + reconfigure)
    # ------------------------------------------------------------------

    def search(self) -> list[LiveCronJob]:
        """Fetch the live job list.

        Returns:
            ``LiveCronJob`` instances normalized from the search rows.

        Raises:
            OpnsenseDriftError: If any row has a malformed identity tag.
        """
        rows = self._cron.search_jobs()
        return [_row_to_live(row) for row in rows if isinstance(row, dict)]

    def add(self, job: CronJobConfig) -> dict[str, Any]:
        """Create a cron job.

        Args:
            job: Desired-state job configuration.

        Returns:
            API response dict.
        """
        return self._cron.add_job(job.to_payload())

    def update(self, uuid: str, job: CronJobConfig) -> dict[str, Any]:
        """Update an existing cron job by UUID.

        Args:
            uuid: UUID of the existing job.
            job: Desired-state job configuration.

        Returns:
            API response dict.
        """
        return self._cron.set_job(uuid, job.to_payload())

    def delete(self, uuid: str) -> dict[str, Any]:
        """Delete a cron job by UUID.

        Args:
            uuid: UUID of the job to delete.

        Returns:
            API response dict.
        """
        return self._cron.del_job(uuid)

    def reconfigure(self) -> dict[str, Any]:
        """Reconfigure the cron service to apply pending changes.

        Called only by the provider's ``_reconfigure_cron`` finalization
        hook — the manager must NOT call this directly.

        Returns:
            API response dict.
        """
        return self._cron.reconfigure()

    # ------------------------------------------------------------------
    # Diff + apply orchestration
    # ------------------------------------------------------------------

    def compute_diff(
        self,
        desired: list[CronJobConfig],
        live: list[LiveCronJob],
        *,
        add_only: bool = False,
    ) -> Diff:
        """Compute the add/update/delete diff.

        Args:
            desired: Desired cron job configurations.
            live: Live cron jobs from the box.
            add_only: If True, suppress deletes.

        Returns:
            ``Diff`` with adds/updates/deletes plus locked entries.
        """
        return compute_diff(desired, live, add_only=add_only)

    def apply_diff(self, diff: Diff) -> dict[str, int]:
        """Dispatch the operations in ``diff``.

        Does **not** call reconfigure — the runner fires the
        ``cron_reconfigure`` finalization hook after all components
        have applied.

        Args:
            diff: Computed diff to apply.

        Returns:
            ``{"created": N, "updated": M, "deleted": K}`` counts.
        """
        created = 0
        updated = 0
        deleted = 0

        for job in diff.adds:
            self.add(job)
            created += 1

        for live_job, want in diff.updates:
            self.update(live_job.uuid, want)
            updated += 1

        for live_job in diff.deletes:
            self.delete(live_job.uuid)
            deleted += 1

        return {"created": created, "updated": updated, "deleted": deleted}

    # ------------------------------------------------------------------
    # Migration / export
    # ------------------------------------------------------------------

    def export_to_yaml(self) -> str:
        """Export the current managed cron jobs to InfraFoundry YAML.

        Only managed jobs (those with the InfraFoundry identity suffix)
        are exported.

        Output is the nested ``opnsense:`` schema (ADR-0016 #793 Phase 4);
        cron jobs land at ``opnsense.cron.jobs`` as a YAML sequence.

        Returns:
            YAML string with the nested ``opnsense:`` namespace and a
            ``cron.jobs`` list leaf.
        """
        live = self.search()
        managed = [j for j in live if j.managed_name is not None]
        entries = [
            {
                "name": j.managed_name,
                "config": _live_to_export_config(j),
            }
            for j in managed
        ]
        return emit_nested_list_yaml("cron.jobs", entries)


# ---------------------------------------------------------------------------
# Internal helpers (row parsing / export)
# ---------------------------------------------------------------------------


def _row_to_live(row: dict[str, Any]) -> LiveCronJob:
    """Normalize a ``searchJobs`` row into a ``LiveCronJob``.

    Args:
        row: Raw row dict from ``searchJobs`` response.

    Returns:
        ``LiveCronJob`` with identity parsed from ``description``.

    Raises:
        OpnsenseDriftError: If the description contains a malformed marker.
    """
    uuid = str(row.get("uuid", ""))
    description = str(row.get("description", "") or "")
    origin = str(row.get("origin", "") or "")
    managed_name, user_description = parse_identity(description)
    return LiveCronJob(
        uuid=uuid,
        managed_name=managed_name,
        description=user_description,
        origin=origin,
        raw=row,
    )


def _live_to_export_config(live: LiveCronJob) -> dict[str, Any]:
    """Build a YAML-friendly config dict from a managed live job.

    Wire keys are mapped back to operator-facing snake_case names.

    Args:
        live: Managed live job to convert.

    Returns:
        Config dict suitable for the ``config:`` block in YAML.
    """
    raw = live.raw
    enabled_raw = raw.get("enabled", "1")
    return {
        "enabled": enabled_raw == "1" if isinstance(enabled_raw, str) else bool(enabled_raw),
        "minutes": str(raw.get("minutes", "*") or "*"),
        "hours": str(raw.get("hours", "*") or "*"),
        # Schedule fields pass through 1:1 — wire keys are days/months/weekdays
        # (verified by live probe 2026-06-18; not mday/month/wday as initially coded).
        "days": str(raw.get("days", "*") or "*"),
        "months": str(raw.get("months", "*") or "*"),
        "weekdays": str(raw.get("weekdays", "*") or "*"),
        "who": str(raw.get("who", "root") or "root"),
        "command": str(raw.get("command", "") or ""),
        "parameters": str(raw.get("parameters", "") or ""),
        "description": live.description,
        # Always emit "cron" in migrated YAML regardless of the live record's
        # origin (e.g. "AcmeClient").  Keeping the live origin would produce YAML
        # that triggers a validator WARNING and then a no-op update on next apply
        # (since origin is excluded from drift detection).  Emitting "cron"
        # ensures the migrated YAML matches what InfraFoundry will write on the
        # wire, making subsequent plans clean.
        "origin": "cron",
    }
