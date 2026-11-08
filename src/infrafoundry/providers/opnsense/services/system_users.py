"""System-users service for OPNsense direct-API operations (ADR-0014, #805).

Manages local users via the ``auth/user`` controller. Identity is the natural-key
wire ``name`` (OPNsense enforces uniqueness). The API has no reconfigure step.

Endpoints (``auth/user``, present in every bundled 26.1.x spec): ``GET search``,
``POST add``, ``POST set/<uuid>``, ``POST del/<uuid>``. Write bodies use the
``{"user": {...}}`` envelope. The ``search`` rows are flat string maps.

Sparse comparison
-----------------

Only the fields the operator set (plus ``name``) are written and compared, so an
existing user such as ``root`` can be declared with just ``uid: 0`` without
clobbering the fields the YAML leaves out. Group membership is owned by
``system.groups``: ``group_memberships`` is never written or compared here.

Secrets
-------

``password``, ``authorizedkeys``, ``otp_seed`` and ``apikeys`` must be written as
``secret://`` URIs in YAML (the validator rejects literals). The manager resolves
them before the diff runs, so this module sees plaintext values only through
``UserConfig.fields`` and never logs them: log lines name changed fields only.

Root protection
---------------

A live user with ``uid == "0"`` is never deleted by the diff, ``apply_diff`` or
the manager's ``destroy``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from infrafoundry.core.provider import ResourceConfig

from .. import endpoints
from .base import BaseService, raise_on_failed_write

logger = logging.getLogger(__name__)

#: Wire fields whose values must come from ``secret://`` URIs.
SECRET_FIELDS: tuple[str, ...] = ("password", "authorizedkeys", "otp_seed", "apikeys")

#: Plain string wire fields an operator may set (``uid``, ``disabled`` and ``priv`` are typed).
_STRING_FIELDS: tuple[str, ...] = (
    "scope",
    "expires",
    "shell",
    "descr",
    "email",
    "comment",
    "language",
    *SECRET_FIELDS,
)
_VALID_SCOPES: frozenset[str] = frozenset({"system", "user"})
_ALLOWED_KEYS: frozenset[str] = frozenset(
    {"name", "lock", "uid", "disabled", "priv", *_STRING_FIELDS}
)
_BCRYPT_RE = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")
ROOT_UID = "0"


@dataclass(frozen=True)
class UserConfig:
    """Desired-state local user.

    Attributes:
        name: Wire user name (diff key).
        fields: Sorted ``(wire_key, serialized_value)`` pairs the operator set.
        lock: Per-resource safety annotation (ADR-0014 section 6).
    """

    name: str
    fields: tuple[tuple[str, str], ...] = ()
    lock: bool = False

    @property
    def diff_key(self) -> str:
        """Identity of this user: the wire ``name``."""
        return self.name

    def field(self, key: str) -> str | None:
        """Return the serialized value of ``key``, or ``None`` when the operator did not set it."""
        for k, v in self.fields:
            if k == key:
                return v
        return None

    def to_payload(self) -> dict[str, Any]:
        """Serialize to the ``add``/``set`` envelope: ``name`` plus the set fields only."""
        return {"user": {"name": self.name, **dict(self.fields)}}


@dataclass(frozen=True)
class LiveUser:
    """A user as currently configured on the box.

    Attributes:
        uuid: OPNsense-assigned UUID.
        name: User name.
        uid: Numeric uid as a string.
        raw: The full ``search`` row.
    """

    uuid: str
    name: str
    uid: str
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def diff_key(self) -> str:
        """Identity of this user: the wire ``name``."""
        return self.name

    @property
    def is_root(self) -> bool:
        """Return True for the uid-0 account, which is never deleted."""
        return self.uid == ROOT_UID


@dataclass
class Diff:
    """Result of comparing desired users to live users."""

    adds: list[UserConfig] = field(default_factory=list)
    updates: list[tuple[LiveUser, UserConfig]] = field(default_factory=list)
    deletes: list[LiveUser] = field(default_factory=list)
    unmanaged: list[LiveUser] = field(default_factory=list)
    locked: list[tuple[UserConfig, LiveUser | None]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if there is nothing to add, update or delete."""
        return not (self.adds or self.updates or self.deletes)


def changed_fields(have: LiveUser, want: UserConfig) -> list[str]:
    """Return the wire keys whose live value differs from the desired one.

    Args:
        have: Live user.
        want: Desired user.

    Returns:
        Field names only, never values (some are secrets).
    """
    changed: list[str] = []
    for key, value in want.fields:
        live_value = _normalize(have.raw.get(key))
        if key == "priv":
            if _priv_set(value) != _priv_set(live_value):
                changed.append(key)
        elif value != live_value:
            changed.append(key)
    return changed


def _needs_update(have: LiveUser, want: UserConfig) -> bool:
    """Return True if any field the operator set differs from the live row."""
    return bool(changed_fields(have, want))


def compute_diff(
    desired: list[UserConfig],
    current: list[LiveUser],
    *,
    add_only: bool = False,
    managed_keys: set[str] | None = None,
) -> Diff:
    """Compare desired users to live users, keyed by ``name``.

    A live user with uid 0 is never deleted, whatever ``managed_keys`` holds.

    Args:
        desired: Users the operator wants.
        current: Users on the box.
        add_only: Suppress deletes.
        managed_keys: When given, only live users in this set may be deleted
            (ADR-0018); others land in ``Diff.unmanaged``.

    Returns:
        The diff.
    """
    desired_by_key = {u.diff_key: u for u in desired}
    current_by_key = {u.diff_key: u for u in current}
    locked_keys = {u.diff_key for u in desired if u.lock}
    diff = Diff()

    for key, want in desired_by_key.items():
        have = current_by_key.get(key)
        if want.lock:
            diff.locked.append((want, have))
        elif have is None:
            diff.adds.append(want)
        elif _needs_update(have, want):
            diff.updates.append((have, want))

    if add_only:
        return diff
    for key, have in current_by_key.items():
        if key in locked_keys or key in desired_by_key:
            continue
        if have.is_root:
            logger.warning("opnsense system.users: refusing to delete the uid 0 account")
            diff.unmanaged.append(have)
        elif managed_keys is not None and key not in managed_keys:
            diff.unmanaged.append(have)
        else:
            diff.deletes.append(have)
    return diff


def user_configs_from_resources(resources: list[ResourceConfig]) -> list[UserConfig]:
    """Convert ``system.users`` resources to :class:`UserConfig`.

    Args:
        resources: Provider resources; other types are skipped.

    Returns:
        Parsed users. Values are kept verbatim, so ``secret://`` URIs stay URIs
        until the manager resolves them.

    Raises:
        ValueError: On a non-dict config, an unknown key or a mistyped value.
    """
    configs: list[UserConfig] = []
    for resource in resources:
        if resource.type != "system.users":
            continue
        config = resource.config
        if not isinstance(config, dict):
            raise ValueError(f"system user '{resource.name}' has non-dict config")
        configs.append(_build_config(resource.name, config))
    return configs


def _build_config(resource_name: str, config: dict[str, Any]) -> UserConfig:
    """Build one :class:`UserConfig`; error messages never include values."""
    unknown = sorted(set(config) - _ALLOWED_KEYS)
    if unknown:
        raise ValueError(f"system user '{resource_name}' has unknown keys: {unknown}")
    name = config.get("name", resource_name)
    if not isinstance(name, str) or not name:
        raise ValueError(f"system user '{resource_name}' requires a non-empty string 'name'")
    lock = config.get("lock", False)
    if not isinstance(lock, bool):
        raise ValueError(f"system user '{resource_name}' lock must be a boolean")

    values: dict[str, str] = {}
    if "uid" in config:
        uid = config["uid"]
        if isinstance(uid, bool) or not isinstance(uid, (int, str)) or not str(uid).isdigit():
            raise ValueError(f"system user '{resource_name}' uid must be a non-negative integer")
        values["uid"] = str(int(uid))
    if "disabled" in config:
        disabled = config["disabled"]
        if not isinstance(disabled, bool):
            raise ValueError(f"system user '{resource_name}' disabled must be a boolean")
        values["disabled"] = "1" if disabled else "0"
    if "priv" in config:
        priv = config["priv"]
        if not isinstance(priv, list) or not all(isinstance(p, str) for p in priv):
            raise ValueError(f"system user '{resource_name}' priv must be a list of strings")
        values["priv"] = ",".join(sorted(set(priv)))
    for key in _STRING_FIELDS:
        if key not in config:
            continue
        value = config[key]
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ValueError(f"system user '{resource_name}' {key} must be a string")
        values[key] = value
    scope = values.get("scope")
    if scope is not None and scope not in _VALID_SCOPES:
        raise ValueError(
            f"system user '{resource_name}' scope must be one of {sorted(_VALID_SCOPES)}"
        )
    return UserConfig(name=name, fields=tuple(sorted(values.items())), lock=lock)


def check_password_hashes(configs: list[UserConfig]) -> None:
    """Require every resolved ``password`` to be a bcrypt hash.

    Args:
        configs: Users after secret resolution.

    Raises:
        ValueError: Naming the user, never the value, when a password is not bcrypt.
    """
    for config in configs:
        password = config.field("password")
        if password and not _BCRYPT_RE.match(password):
            raise ValueError(
                f"system user '{config.name}' password must resolve to a bcrypt hash "
                f'("$2y$NN$..."); plaintext passwords are not accepted'
            )


def _normalize(value: Any) -> str:
    """Collapse a live field value to a comparable string."""
    if value is None:
        return ""
    if isinstance(value, dict):
        for option_key, option_value in value.items():
            if isinstance(option_value, dict) and option_value.get("selected"):
                return str(option_key)
        return ""
    return str(value)


def _priv_set(value: str) -> frozenset[str]:
    """Split a comma-separated privilege string into a set."""
    return frozenset(p.strip() for p in value.split(",") if p.strip())


def search_rows(response: Any) -> list[dict[str, Any]]:
    """Return the dict rows of a ``search`` response, tolerating malformed bodies."""
    if isinstance(response, dict):
        rows = response.get("rows")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    return []


def row_to_live(row: dict[str, Any]) -> LiveUser:
    """Normalize a ``search`` row into a :class:`LiveUser`."""
    return LiveUser(
        uuid=str(row.get("uuid", "")),
        name=str(row.get("name", "")),
        uid=_normalize(row.get("uid")),
        raw=row,
    )


class UserService(BaseService):
    """Service for OPNsense local-user operations via the ``auth/user`` controller."""

    def search(self) -> list[LiveUser]:
        """Fetch the live users."""
        ep = endpoints.AUTH_USER.search
        return [row_to_live(r) for r in search_rows(self.client.request(ep.method, ep.path()))]

    def add(self, user: UserConfig) -> dict[str, Any]:
        """Create a user; raises when OPNsense rejects it."""
        ep = endpoints.AUTH_USER.add
        response = self.client.request(ep.method, ep.path(), data=user.to_payload())
        return raise_on_failed_write(response, f"add user {user.name}")  # type: ignore[no-any-return]

    def update(self, uuid: str, user: UserConfig) -> dict[str, Any]:
        """Update a user by UUID; raises when OPNsense rejects it."""
        ep = endpoints.AUTH_USER.update
        response = self.client.request(ep.method, ep.path(uuid=uuid), data=user.to_payload())
        return raise_on_failed_write(response, f"update user {user.name}")  # type: ignore[no-any-return]

    def delete(self, live: LiveUser) -> dict[str, Any] | None:
        """Delete a user by UUID. The uid-0 account is never deleted.

        Args:
            live: The live user to delete.

        Returns:
            The response, or ``None`` when the user is protected.
        """
        if live.is_root:
            logger.warning("opnsense system.users: refusing to delete the uid 0 account")
            return None
        ep = endpoints.AUTH_USER.delete
        response = self.client.request(ep.method, ep.path(uuid=live.uuid))
        return raise_on_failed_write(response, f"delete user {live.name}")  # type: ignore[no-any-return]

    def compute_diff(
        self,
        desired: list[UserConfig],
        live: list[LiveUser],
        *,
        add_only: bool = False,
        managed_keys: set[str] | None = None,
    ) -> Diff:
        """Service-method form of :func:`compute_diff`."""
        return compute_diff(desired, live, add_only=add_only, managed_keys=managed_keys)

    def apply_diff(self, diff: Diff) -> dict[str, int]:
        """Dispatch the diff. There is no reconfigure step for users.

        Returns:
            ``{"created": N, "updated": M, "deleted": K}``.
        """
        created = updated = deleted = 0
        for user in diff.adds:
            self.add(user)
            created += 1
        for live, want in diff.updates:
            logger.info(
                "opnsense system.users: updating %s (fields: %s)",
                want.name,
                changed_fields(live, want),
            )
            self.update(live.uuid, want)
            updated += 1
        for live in diff.deletes:
            if self.delete(live) is not None:
                deleted += 1
        return {"created": created, "updated": updated, "deleted": deleted}
