# k3s-kubeconfig-mode

Keeps the node kubeconfig (`k3s.yaml`) readable by its owner only on an
existing control node. It sets `write-kubeconfig-mode: "0600"` in
the k3s `config.yaml` (replacing any existing line, leaving the rest of the file
alone) and sets the kubeconfig's mode when the file exists. It restarts nothing.

Run by `blueprints/k3s-cluster/playbooks/k3s-kubeconfig-mode.yml`, which
`blueprints/k3s-cluster/scripts/oci/k3s-kubeconfig-mode.sh` starts on every apply.
