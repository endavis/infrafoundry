"""Detect terraform state that no current package declares (#1459).

Renaming a blueprint package changes the terraform address of its resources, so the old
resources stay in state while the new ones are created. When both carry the same VM id the
create collides. These helpers are pure: they read ``.tf`` files and already-parsed terraform
output, and never run terraform.
"""

import re
from pathlib import Path
from typing import Any

_RESOURCE_RE = re.compile(r'^resource\s+"([^"]+)"\s+"([^"]+)"')
_MODULE_RE = re.compile(r'^module\s+"([^"]+)"')
_BLOCK_END_RE = re.compile(r"^\}")
# A resource's own ``vm_id`` sits two spaces in; nested blocks (``clone {}``) are deeper.
_TOP_VM_ID_RE = re.compile(r"^  vm_id\s*=\s*(\d+)\s*$")
_TRIGGER_VMID_RE = re.compile(r'^\s+vmid\s*=\s*"(\d+)"')
_INDEX_RE = re.compile(r"\[[^\]]*\]$")


def normalize_state_address(address: str) -> str | None:
    """Reduce a state address to the form the ``.tf`` files declare.

    Args:
        address: Address from ``terraform state list``

    Returns:
        ``None`` for data sources; ``module.<name>`` for anything inside a module;
        otherwise the address without a trailing ``[index]``.
    """
    if address.startswith("data."):
        return None
    if address.startswith("module."):
        head = address.split(".", 2)[1]
        return "module." + _INDEX_RE.sub("", head)
    return _INDEX_RE.sub("", address)


def declared_modules(tf_dir: Path) -> set[str]:
    """Return the names of the ``module`` blocks declared in the ``.tf`` files."""
    modules: set[str] = set()
    for tf_file in tf_dir.glob("*.tf"):
        for line in tf_file.read_text(encoding="utf-8").splitlines():
            match = _MODULE_RE.match(line)
            if match:
                modules.add(match.group(1))
    return modules


def orphaned_addresses(
    in_state: list[str], declared_resources: set[str], modules: set[str]
) -> list[str]:
    """Return state addresses that no current package declares.

    Args:
        in_state: Addresses from ``terraform state list``
        declared_resources: ``type.name`` addresses declared in the ``.tf`` files
        modules: Names of the declared ``module`` blocks

    Returns:
        The original state addresses, without duplicates, in state order.
    """
    orphans: list[str] = []
    for address in in_state:
        normalized = normalize_state_address(address)
        if normalized is None:
            continue
        if normalized.startswith("module."):
            declared = normalized.removeprefix("module.") in modules
        else:
            declared = normalized in declared_resources
        if not declared and address not in orphans:
            orphans.append(address)
    return orphans


def declared_vm_ids(tf_dir: Path) -> dict[str, str]:
    """Map each declared resource address to the VM id it sets.

    Reads a top-level ``vm_id = <n>`` or a ``vmid = "<n>"`` trigger. Resources without
    either are absent.
    """
    ids: dict[str, str] = {}
    for tf_file in tf_dir.glob("*.tf"):
        current: str | None = None
        for line in tf_file.read_text(encoding="utf-8").splitlines():
            match = _RESOURCE_RE.match(line)
            if match:
                current = f"{match.group(1)}.{match.group(2)}"
                continue
            if current is None:
                continue
            if _BLOCK_END_RE.match(line):
                current = None
                continue
            vm = _TOP_VM_ID_RE.match(line) or _TRIGGER_VMID_RE.match(line)
            if vm:
                ids.setdefault(current, vm.group(1))
    return ids


def _walk_module(module: dict[str, Any], ids: dict[str, str]) -> None:
    for resource in module.get("resources", []) or []:
        if resource.get("mode") != "managed":
            continue
        values = resource.get("values") or {}
        vm_id = values.get("vm_id")
        if vm_id is None:
            triggers = values.get("triggers_replace")
            if isinstance(triggers, dict):
                vm_id = triggers.get("vmid")
        address = resource.get("address")
        if vm_id is not None and address:
            ids[str(address)] = str(vm_id)
    for child in module.get("child_modules", []) or []:
        _walk_module(child, ids)


def state_vm_ids(show_json: dict[str, Any]) -> dict[str, str]:
    """Map each managed resource address in ``terraform show -json`` to its VM id."""
    ids: dict[str, str] = {}
    root = (show_json.get("values") or {}).get("root_module")
    if isinstance(root, dict):
        _walk_module(root, ids)
    return ids


def find_vmid_collisions(
    new: dict[str, str], orphans: dict[str, str]
) -> list[tuple[str, str, str]]:
    """Pair each new resource with the orphan that holds its VM id.

    Returns:
        ``(new_address, vm_id, orphan_address)`` tuples.
    """
    holder = {vm_id: address for address, vm_id in orphans.items()}
    return [(addr, vm_id, holder[vm_id]) for addr, vm_id in new.items() if vm_id in holder]


def orphan_warning(provider: str, env: str | None, orphans: list[str], filtered: bool) -> str:
    """Build the warning listing orphaned state addresses."""
    env_label = env or "<env>"
    listed = ", ".join(orphans)
    effect = "this filtered run leaves them in place" if filtered else "this run destroys them"
    return (
        f"Warning: {provider} state holds resources no package declares: {listed}; {effect}. "
        f"To remove them, restore the package that declared them and run "
        f"'foundry infra destroy --env {env_label} -p <old-package>'."
    )


def collision_message(
    provider: str, env: str | None, collisions: list[tuple[str, str, str]]
) -> str:
    """Build the refusal message for VM ids still held by orphaned resources."""
    env_label = env or "<env>"
    lines = [
        f"{provider}: a new resource reuses the VM id of a resource in state that no package "
        "declares (a renamed package?). Creating it would collide."
    ]
    lines.extend(
        f"  {new} wants VM id {vm_id}, held by orphaned {orphan}"
        for new, vm_id, orphan in collisions
    )
    lines.append(
        "Restore the old package, run "
        f"'foundry infra destroy --env {env_label} -p <old-package>', "
        "then apply the renamed one."
    )
    return "\n".join(lines)
