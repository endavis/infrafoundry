# ADR-0003: Multi-provider blueprint support

## Status

Accepted

## Context

Blueprints currently hardcode provider-specific resource schemas. The `proxmox-k3s-cluster` and `oci-k3s-cluster` blueprints duplicate the same intent (k3s cluster with server and agent nodes) in completely different syntax. Adding ESXi or AWS support would mean more duplication.

The orchestrator is already provider-agnostic, routing by `provider` field and calling abstract methods. The gap is at the resource configuration level: no shared schema exists between providers.

Two approaches were considered:

1. **Base schema abstraction layer** -- define abstract compute/network/storage fields and translate to provider-native syntax at generation time.
2. **Provider-conditional resource file selection** -- keep provider-native resource templates but let a single blueprint declare which resource files to use per provider.

Related issue: [#507](https://github.com/endavis/infrafoundry/issues/507)

## Decision

Use provider-conditional resource file selection rather than a new schema abstraction layer.

A blueprint's `blueprint.yaml` gains an optional `providers:` section that maps provider names to resource file lists and optional provider-specific defaults:

```yaml
providers:
  proxmox:
    resources:
      - providers/proxmox/vm.yaml
    defaults:
      target_node: pve1
  oci:
    resources:
      - providers/oci/instance.yaml
```

The PackageLoader selects the correct resource set based on the package's `provider` value. The defaults merge order is: `blueprint.defaults < providers[x].defaults < package.variables`.

Blueprints without a `providers:` section continue to work unchanged.

See [Package Loader](../architecture/package-loader.md) for implementation details (to be created in Phase 2).

## Consequences

**Easier:**
- A single blueprint can serve multiple providers, deduplicating shared defaults, scripts, events, and inventory
- Zero migration cost for existing single-provider blueprints
- Provider expertise stays in provider-native templates with no lossy translation
- Shared variables (e.g., `server_cores`) naturally feed into both `cores: {{ server_cores }}` (Proxmox) and `ocpus: {{ server_cores }}` (OCI) via Jinja2

**Harder:**
- No schema validation across providers -- no guarantee that Proxmox and OCI templates consume the same variables
- No automatic field mapping -- blueprint authors still write provider-specific templates
- Still need N resource file sets for N providers (but shared defaults, scripts, and events are deduplicated)

These are acceptable tradeoffs. The real duplication today is in the non-resource parts (scripts, ansible, defaults, events) which this design fully deduplicates.
