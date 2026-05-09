"""Shared dotted-path cross-reference resolver for OPNsense validators (#793).

Provides a single resolver used by every validator that has cross-resource
fields (gateway lookups, alias targets, host-override targets, future
acmeclient cert→account refs, etc.). Centralising the logic here keeps
the per-validator code focused on field-shape checks and avoids
duplicating the dotted-path parsing across each validator.

Cross-reference syntax (per ADR-0016):

- ``<name>`` — bare name, relative within the validator's expected type.
  Today's flat schema uses this form exclusively (e.g. ``gateway:
  WAN_GW`` references ``routing.gateways`` by bare name); behaviour is
  unchanged.
- ``<sub>.<name>`` — in-plugin relative. Resolves within the current
  plugin context (e.g. ``account: accounts.letsencrypt-prod`` from a
  resource declared under ``acmeclient`` resolves to type
  ``acmeclient.accounts``, name ``letsencrypt-prod``).
- ``<plugin>.<sub>.<name>`` (or deeper) — cross-plugin absolute.
  Fully qualified path including the target plugin (e.g.
  ``update_cron: cron.jobs.acmeclient-auto-renew``). Used when the
  reference crosses plugin boundaries.

The resolver is intentionally non-strict on the target's existence —
it returns ``None`` on a miss and lets the caller decide error
severity (``ERROR`` for managed-only refs, ``WARNING`` plus a
managed-or-live fallback for the OPNsense pattern of accepting either
a YAML resource name or a live API row).

Malformed values (empty string, leading/trailing dots, multiple
consecutive dots) raise ``ValueError`` because they indicate a
programming error or grossly malformed YAML — those are surfaced by
the loader / per-field type checks, not by the cross-reference layer.
"""

from __future__ import annotations

from infrafoundry.core.provider import ResourceConfig

# Public alias for the index shape used throughout this module. The
# nested-dict shape (``{dotted_type: {resource_name: ResourceConfig}}``)
# gives O(1) lookup per resolver call; building it once at the start of
# validation keeps the per-resource validators cheap.
XRefIndex = dict[str, dict[str, ResourceConfig]]


def build_xref_index(resources: list[ResourceConfig]) -> XRefIndex:
    """Build a dotted-type index of resources for cross-reference lookup.

    Walks the resource list once, grouping by ``resource.type`` and
    keying the inner dict by ``resource.name``. Used by
    ``OPNsenseValidator.validate()`` (called once at validation start)
    to feed each per-resource validator.

    Args:
        resources: All resources in the current environment (already
            loaded from YAML by ``package_loader``).

    Returns:
        Nested dict: ``{dotted_type: {resource_name: ResourceConfig}}``.
        Empty if ``resources`` is empty. Resources sharing the same
        ``(type, name)`` collide silently — uniqueness is enforced by
        ``ResourceNameValidator``, not here.
    """
    index: XRefIndex = {}
    for resource in resources:
        index.setdefault(resource.type, {})[resource.name] = resource
    return index


def resolve_xref(
    value: str,
    expected_type: str,
    index: XRefIndex,
    current_plugin: str | None = None,
) -> ResourceConfig | None:
    """Resolve a cross-reference value against the dotted-type index.

    Accepts the three forms described in this module's docstring (bare
    name, in-plugin relative, cross-plugin absolute) and returns the
    matched ``ResourceConfig`` or ``None`` if no resource matches the
    parsed ``(type, name)`` tuple.

    Args:
        value: The cross-reference value as written in YAML
            (e.g. ``"WAN_GW"``, ``"accounts.letsencrypt-prod"``,
            ``"cron.jobs.acmeclient-auto-renew"``).
        expected_type: The dotted type the validator expects when the
            value is a bare name (e.g. ``"routing.gateways"``,
            ``"firewall.aliases"``). Ignored when ``value`` carries a
            dot-qualified path.
        index: The dotted-type index built by ``build_xref_index``.
        current_plugin: The plugin name to use when resolving the
            in-plugin relative form (e.g. ``"acmeclient"``). Required
            for the single-dot form; ignored for bare names and fully
            qualified paths. ``None`` means in-plugin relative refs are
            unresolvable (the caller is responsible for surfacing that
            as an error if the value contains a dot).

    Returns:
        The matched ``ResourceConfig`` or ``None`` on miss.

    Raises:
        ValueError: If ``value`` is empty, has leading/trailing dots,
            or contains consecutive dots — those indicate either a
            programming error or grossly malformed YAML the loader
            should have rejected. Single-dot values without a
            ``current_plugin`` are *not* rejected here (they parse
            cleanly but resolve to ``None``); the caller can surface a
            clearer error in that case.
    """
    if not value:
        raise ValueError("cross-reference value must be non-empty")
    if value.startswith(".") or value.endswith("."):
        raise ValueError(f"cross-reference value {value!r} must not start or end with a '.'")
    if ".." in value:
        raise ValueError(f"cross-reference value {value!r} must not contain consecutive dots")

    parts = value.split(".")

    if len(parts) == 1:
        # Bare name — look up in the validator's expected type.
        return _lookup(index, expected_type, parts[0])

    if len(parts) == 2:
        # In-plugin relative form: ``<sub>.<name>``. Without a current
        # plugin we can't resolve — return None and let the caller fall
        # back to bare-name lookup or surface an error.
        if current_plugin is None:
            return None
        sub, name = parts
        full_type = f"{current_plugin}.{sub}"
        return _lookup(index, full_type, name)

    # Cross-plugin absolute form: ``<plugin>.<sub>...<name>``. The last
    # segment is the resource name; everything before it composes the
    # dotted type. This naturally supports deeper nesting like
    # ``kea.dhcp4.subnets.<name>`` (type ``kea.dhcp4.subnets``).
    name = parts[-1]
    full_type = ".".join(parts[:-1])
    return _lookup(index, full_type, name)


def _lookup(index: XRefIndex, dotted_type: str, name: str) -> ResourceConfig | None:
    """Return ``index[dotted_type][name]`` or ``None`` on miss.

    Pulled out so the three resolution branches share one lookup path
    and the per-branch logic stays focused on parsing.
    """
    type_bucket = index.get(dotted_type)
    if type_bucket is None:
        return None
    return type_bucket.get(name)
