# reverse-proxy (example)

Example consumer of the [reverse-proxy blueprint](../../../../../../blueprints/reverse-proxy/README.md).
It serves two device web UIs, `nas.example.com` and `switch.example.com`, from one Caddy VM
at `192.0.2.70`. The addresses are documentation addresses; replace them.

First deployment, in order:

1. `foundry secrets host-keys --env dev`
2. `foundry infra apply --env dev --package reverse-proxy`
3. `foundry certs issue --env dev`
4. `foundry infra apply --env dev --package reverse-proxy` again, which writes the Caddyfile.

The certificate needs the `acme` provider enabled for the environment; remove
`certificate_names` to deploy without it. See the [guide](../../../../../../docs/guides/reverse-proxy.md).
