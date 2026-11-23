# NetApp Console agent — Example

Example package consuming the `console-connector` blueprint. All deployment
logic lives in `blueprints/console-connector/`; this directory only supplies the
per-instance values.

See `blueprints/console-connector/README.md` for the variable reference,
prerequisites and the manual registration steps.

## Quick Start

```bash
# Record the VM's pinned SSH host key first (needed once, and after upgrading)
foundry secrets host-keys --env dev --package console-connector

# Deploy the VM, DHCP reservation and the agent install
foundry infra apply --env dev --package console-connector

# Destroy (also deregisters the agent when the service account inputs are set)
foundry infra destroy --env dev --package console-connector
```

Replace the placeholder installer URL, installer file name and jumphost before
applying. Registration in the NetApp Console is a manual browser step unless you set
`console_client_id`, `console_client_secret` (in a SOPS `secrets.yaml`) and
`console_admin_email`; see the blueprint README, "Scripted registration".
