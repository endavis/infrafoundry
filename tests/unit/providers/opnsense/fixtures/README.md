# OPNsense Provider Schema Fixture

`browningluke_opnsense_schema.json` is a pinned snapshot of the
`browningluke/opnsense` Terraform provider's resource attribute schema, used
by `tests/unit/providers/opnsense/test_template_schema_compliance.py` to
guard against InfraFoundry's `*.tf.j2` templates rendering argument names
the provider doesn't accept (the `Unsupported argument` class of bug
fixed by #765).

The JSON is an object mapping each `opnsense_*` resource type the
framework currently emits to a sorted list of supported attribute names
(both settable and computed/read-only — the test only checks that
rendered argument names appear in the list, since computed attributes
won't be rendered by the templates anyway).

## Regenerate when the provider pin bumps

The `browningluke/opnsense` pin lives in
`src/infrafoundry/providers/opnsense/templates/opnsense/provider.tf.j2`.
When that pin changes, regenerate this fixture against the new version:

```bash
cd generated/<env>/terraform/opnsense  # any env that has run `infra plan`
terraform providers schema -json \
  | jq '.provider_schemas["registry.terraform.io/browningluke/opnsense"].resource_schemas | map_values(.block.attributes | keys)' \
  > /path/to/infrafoundry/tests/unit/providers/opnsense/fixtures/browningluke_opnsense_schema.json
```

If the test starts failing after a regen, that's the schema-compliance
guard doing its job — investigate which template needs updating.

## Scope

Only resource types InfraFoundry's templates currently emit are listed:

- `opnsense_firewall_alias` (from `aliases.tf.j2`)
- `opnsense_kea_reservation` (from `kea_reservation.tf.j2`)
- `opnsense_kea_subnet` (from `kea_subnet.tf.j2`)
- `opnsense_unbound_host_override` (from `unbound_host_override.tf.j2`)

`dhcp_static_maps.tf.j2` is intentionally excluded — it references
`opnsense_dhcpv4_static_map`, a resource type that doesn't exist in the
current `browningluke/opnsense` provider. Resolution (delete the template
or port to `opnsense_kea_reservation`) is tracked as a follow-up to #765
and out of scope for the schema-compliance fixture.
