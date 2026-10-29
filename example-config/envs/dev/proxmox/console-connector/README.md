# NetApp Console agent — Example

Example package consuming the `console-connector` blueprint. All deployment
logic lives in `blueprints/console-connector/`; this directory only supplies the
per-instance values.

See `blueprints/console-connector/README.md` for the variable reference,
prerequisites and the manual registration steps.

## Quick Start

```bash
# Deploy the VM, DHCP reservation and the agent install
foundry infra apply --env dev --package console-connector

# Destroy (deregister the agent in the NetApp Console first)
foundry infra destroy --env dev --package console-connector
```

Replace the placeholder installer URL, installer file name and jumphost before
applying. Registration in the NetApp Console is a manual browser step.
