# k3s-bootstrap role

Creates the `ansible` login user on every OCI k3s node. A fresh image only has
`ubuntu`, so the role connects as `ubuntu`; every other connection then uses
`ansible`.

The role is idempotent and standalone. It never touches k3s services, never
removes users or keys, and uses only `ansible.builtin` modules.

## What it does

- Creates the user with a home directory and `/bin/bash`.
- Creates `~/.ssh` (mode 0700) and adds each public key to `authorized_keys`
  (mode 0600), leaving other keys alone.
- Writes `/etc/sudoers.d/90-<user>` with `NOPASSWD:ALL` (mode 0440), checked
  with `visudo -cf` before it is installed.

## Variables

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `k3s_bootstrap_user` | `ansible` | Login user to create |
| `k3s_bootstrap_ssh_public_keys` | `[]` | Keys to authorize; must not be empty |
| `k3s_bootstrap_shell` | `/bin/bash` | Login shell |

`blueprints/k3s-cluster/scripts/oci/k3s-post-terraform.sh` (on create) and
`blueprints/k3s-cluster/scripts/oci/k3s-bootstrap.sh`
(on every apply) run it through `blueprints/k3s-cluster/playbooks/k3s-bootstrap.yml`.
