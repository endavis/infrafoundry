# ADR-0005: Provider-owned CLI commands discovered via entry points

## Status

Accepted

Related issue: [#626](https://github.com/endavis/infrafoundry/issues/626)

## Context

Provider-specific operations were starting to accumulate as flags and
`--provider` arguments inside generic command groups. The first concrete
instance was `foundry config export --provider proxmox`, which takes
filters (`--node`, `--resource-type`) that only make sense for Proxmox,
inside a `config` group whose job is supposed to be the generic
configuration surface. The issue that motivated this decision (#626) then
needed a second, different provider-specific command —
`foundry ... dump ...` — for raw API snapshots. Putting that under
`config` would have compounded the problem; putting it under `infra`
would have been worse (`infra` is for plan/apply/drift, not read-only
audit commands).

Separately, the framework already shipped an unused plugin-discovery
infrastructure aimed at exactly this case:

- `ProviderMetadata.cli_registration`
  (`src/infrafoundry/providers/plugin_type.py:49`) is a documented
  callback field designed for providers to register CLI commands.
- The `infrafoundry.providers` entry point group was defined in
  `pyproject.toml` but had zero registered providers, so discovery
  returned an empty list and the callback never fired.
- `PluginDiscovery.discover_plugins`
  (`src/infrafoundry/core/plugin_system/discovery.py`) already scans the
  group and runs per-plugin validation.

In other words, the scaffolding existed but had never been wired up for
an actual user-visible feature. Every provider-specific command that
landed before this one therefore lived under a generic CLI group and
hardcoded its provider name in a flag.

`docs/plugin_system/CLI_DESIGN.md` originally sketched `foundry proxmox
info` / `foundry proxmox vm list` as the target surface — i.e. providers
at the top level of the CLI. That design predates any implementation and
was written before `config`/`infra`/`state` had stabilised as
top-level groups. Putting each provider at the top level would collide
with that taxonomy (`foundry proxmox` alongside `foundry infra` and
`foundry config`) and make discovery ambiguous.

## Decision

Provider-specific CLI commands live under a dedicated top-level
`foundry provider <name>` group, and each provider owns its own CLI code
inside its package.

**Surface:**

- `foundry provider` is a top-level Click group introduced in this ADR.
- Each discovered provider gets a subgroup named after it
  (`foundry provider proxmox`, in time `foundry provider opnsense`, etc.).
- Provider subcommands live under that subgroup
  (`foundry provider proxmox dump`, `foundry provider proxmox export`).

**Extension mechanism:**

- A provider package exposes a `register()` function returning
  `ProviderMetadata` via the `infrafoundry.providers` entry point in its
  `pyproject.toml`.
- `ProviderMetadata.cli_registration` is a callable accepting a
  `click.Group`. The framework creates the subgroup and passes it in; the
  provider adds its own subcommands to it.
- Provider CLI modules live inside the provider package at
  `providers/<name>/cli/` — next to that provider's validators, API
  client, and exporters. Nothing provider-specific lives under
  `src/infrafoundry/cli/commands/` anymore.

**Lazy discovery:**

- The `provider` group's `list_commands` and `get_command` methods
  trigger discovery on first invocation, not at module import time.
  This avoids an import cycle: provider CLI modules depend on
  `infrafoundry.cli.utils` (for `console`/`raise_cli_error`), whose
  parent package would otherwise re-enter the discovery loop while the
  provider package is still initialising.
- Discovery failures are logged, never raised: a broken third-party
  plugin cannot take down the rest of the CLI.

**Breaking change:**

- `foundry config export --provider proxmox` moves to
  `foundry provider proxmox export` with no deprecation window.
  InfraFoundry is still pre-1.0; the `--provider proxmox` flag only had
  one valid value so the migration is mechanical. CHANGELOG notes it.

**Supersedes the CLI_DESIGN sketch of `foundry <provider>`:** the
`foundry provider <name>` taxonomy wins because it keeps `foundry`'s
top-level stable (`config`, `infra`, `state`, `secrets`, `policy`,
`provider`, `doctor`, `completion`) regardless of how many providers
ship, and makes it obvious at a glance which commands are
provider-scoped.

## Consequences

**Easier:**

- Third-party provider packages can ship their own CLI by shipping a
  `register()` entry point. No framework change required.
- `config` and `infra` are free of provider-specific flags. Each
  command's options map one-to-one with what it actually does.
- A new provider's CLI code stays inside the provider package, so the
  3-layer stack (provider → component manager → service layer) gets a
  fourth, optional layer — provider CLI — that lives where the rest of
  its code does.
- The ADR gives future contributors a single place to read how to add
  CLI to a provider.

**More difficult:**

- `foundry config export --provider proxmox` no longer works. The pool
  of affected callers is this repo and the user's private
  `endavis-infra` config repo (no scripts currently exercise it).
- `ProviderPluginType.validate_plugin` previously required a CRUD API
  (`create`/`read`/`update`/`delete`/`list_resources`) that no real
  `ProviderBase` subclass implements. This ADR's implementation
  loosened those required methods to match `ProviderBase`'s actual
  abstract surface (`validate_config`, `generate_terraform`,
  `generate_ansible`, `get_resource_types`). Validation is now honest
  but less strict than the original aspirational design.

**Neutral:**

- CLI startup does one additional entry-point scan. The scan is already
  used for secret backends and takes microseconds.
- The existing `ProviderPluginType.register_cli` method (which creates
  subgroups and calls `cli_registration`) is no longer used by the new
  `provider` group; the group runs its own equivalent loop via
  `PluginDiscovery.discover_plugins` + `cli_registration`. That method
  is now dead code with respect to the CLI but kept for compatibility
  with any out-of-tree callers.

## Implementation

- Top-level group: `src/infrafoundry/cli/commands/provider/__init__.py`
- Proxmox registration: `src/infrafoundry/providers/proxmox/__init__.py`
  (`register` + `register_cli`)
- Proxmox CLI package: `src/infrafoundry/providers/proxmox/cli/`
  (`dump.py`, `export.py`)
- Entry point: `[project.entry-points."infrafoundry.providers"]` in
  `pyproject.toml`
- Plugin validation fix:
  `src/infrafoundry/providers/plugin_type.py::ProviderPluginType.validate_plugin`
- Tests:
  - `tests/unit/cli/test_provider_group.py`
  - `tests/unit/providers/proxmox/cli/test_dump.py`
  - `tests/unit/providers/proxmox/cli/test_export.py`
  - `tests/unit/providers/proxmox/test_dumper.py`
- Documentation:
  - [Proxmox provider guide](../providers/proxmox.md)
  - [CLI reference](../usage/cli-reference.md) — updated `config export`
    entry, added `provider proxmox dump` section
  - [Plugin system CLI design](../plugin_system/CLI_DESIGN.md) —
    addendum noting this ADR supersedes the `foundry <provider>` sketch
