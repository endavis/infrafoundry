---
title: "Host Provider"
description: "Configure machines that already exist and that no provider creates, with Ansible playbooks and Tailscale enrollment"
audience:
  - users
tags:
  - providers
---

# Host Provider

The host provider configures a machine that already exists. A typical case is a VPS on a long-term contract whose host offers no management API. InfraFoundry never creates, rebuilds or deletes the machine: it records the host in the state database, runs Ansible against it on `infra apply`, and only forgets it on `infra destroy`.

## Supported Resources

| Type | Description |
|------|-------------|
| `host` | An existing machine reachable over SSH |

## Configuration

Host resources go in `envs/<env>/host/host.yaml` under a top-level `host:` key, and the provider is listed in the environment's `settings.yaml`:

```yaml
# envs/prod/settings.yaml
name: prod
providers:
  - host
```

```yaml
# envs/prod/host/host.yaml
host:
  - name: vps-01
    address: vps-01.example.com      # or 192.0.2.10 / 2001:db8::10
    ssh_user: admin
    ssh_port: 22
    ssh_private_key_file: ~/.ssh/id_example
    groups: [webservers]
    ansible:
      playbooks:
        - playbooks/base.yml
    tailscale:
      auth:
        oauth:
          client_id_secret: tailscale.oauth_client_id
          client_secret_secret: tailscale.oauth_client_secret
      advertise_tags: [tag:example]
```

`client_id_secret`, `client_secret_secret` and `auth_key_secret` take a dotted secret path or a `secret://env_secrets/...` or `secret://bitwarden/...` URI. See [Bitwarden / Vaultwarden secret backend](../configuration/secrets-vaultwarden.md).

| Field | Meaning |
| :--- | :--- |
| `name` | Host name; the inventory host and the resource name. |
| `address` | Required. An IPv4 or IPv6 address or a DNS name. It must not start with `-`. |
| `ssh_user` | Login user. Defaults to Ansible's default (the current user). |
| `ssh_port` | SSH port, 1 to 65535. Default 22. |
| `ssh_private_key_file` | Private key path passed to SSH and Ansible. |
| `groups` | Ansible inventory groups. Names match `[A-Za-z_][A-Za-z0-9_]*`. |
| `ansible.playbooks` | Playbooks run against the host, in order. Paths are relative to the config repo and must stay inside it. |
| `tailscale` | Enrollment block; see below. |

Unknown keys are reported as warnings.

## What Apply Does

`foundry infra apply --env prod` writes `generated/prod/ansible/host/` (`inventory.yml`, `ansible.cfg` and, when a host has a `tailscale:` block, `tailscale.yml`) and then runs, for each host, `ansible-playbook -i inventory.yml --limit <host> <playbook>`: the enrollment playbook first, then the host's own playbooks. The Ansible `roles_path` is the config repo's `roles/` directory. The generated `ansible.cfg` sets `host_key_checking = True`, so each host's key must be in your `~/.ssh/known_hosts` (see [SSH Host Key Checking](../guides/ssh-host-key-checking.md)).

The host is a tracked resource. It appears in `infra deployed`, and `-r vps-01` and `-P host` scope a run to it. The first apply records a `create`, later ones an `update`, so `on_create` and `on_update` handlers fire. The generated Terraform is an empty `terraform {}` block, since nothing is managed through Terraform.

The playbooks themselves must be idempotent: they run on every apply.

## Tailscale

The `tailscale:` block is the one the [cloud instances take](tailscale.md#instance-tailscale-block) and is validated the same way. Differences:

- Enrollment runs at apply through a built-in playbook. It installs Tailscale when missing, skips a host that is already `Running`, and otherwise runs `tailscale up` with the settings of the block.
- `additional_parts` is cloud-init only and is an error here.
- `advertise_exit_node` is cloud-init only and is an error here.
- The auth secret is passed to that run in the `INFRAFOUNDRY_TAILSCALE_AUTH_KEY` environment variable. The playbook writes it to a mode 0600 temporary file on the host, passes it as `--auth-key=file:<path>`, and removes the file afterwards. It is never written to the inventory or to the controller's disk, and tasks that handle it use `no_log`.
- On `infra destroy`, [tailnet device removal](tailscale.md#removing-the-tailnet-device-on-destroy) applies to the host like any other resource.

## Destroy

`foundry infra destroy --env prod -r vps-01` marks the host `DELETED` in the state database, fires its `on_destroy` handlers and removes its tailnet device. It never contacts the machine, and the machine, Tailscale on it and anything the playbooks installed stay as they are.

Removing a host from the YAML does not forget it. Run `infra destroy -r <host>` first.

## Doctor

`foundry infra doctor --env prod -P host` checks the schema, the `tailscale:` secret references, that `ansible-playbook` is installed (a warning when not), and that each host accepts an SSH login (`ssh -o BatchMode=yes -o ConnectTimeout=10 ... true`). The key must work without a prompt.

## Not Covered

- Drift detection: InfraFoundry does not compare the machine with its configuration.
- Creating or rebuilding the machine.

## Related

- [ADR-0022](../decisions/0022-existing-hosts-are-configured-through-a-host-provider-and-runner-that-never-create-or-delete-the-machine.md)
- [Tailscale Provider](tailscale.md)
