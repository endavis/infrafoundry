# Engineering spikes

Throw-away code that produces evidence for an ADR. Each spike pairs with a findings doc under `docs/development/`. Spikes ship or get deleted on their own merits — they do not modify production code.

## `interface_assignment_gist_rest/` — graduated to production in #720

Deleted in PR for #720. The gist-based REST write path graduated from
this spike directory to `src/infrafoundry/providers/opnsense/extensions/interface_assignments/`.
The historical spike findings remain at
[`docs/development/opnsense-spike-interface-assignment-gist-findings.md`](../../docs/development/opnsense-spike-interface-assignment-gist-findings.md);
ADR-0014's per-component decisions section records the graduated mechanism.
