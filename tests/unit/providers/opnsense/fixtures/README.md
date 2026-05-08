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

After the OPNsense cutover-unblock series (#775 / #776 / #758 / #777 / #778
/ #782), all OPNsense components are managed by `OPNsenseDirectRunner` —
no terraform templates remain in scope. The fixture is retained so a
future terraform-managed component (if any is introduced) can be wired
into `test_template_schema_compliance.py` without re-running the
provider-schema extraction from scratch.

The fixture's keys are the `opnsense_*` resource types that *were*
emitted by historical templates: `opnsense_kea_reservation`,
`opnsense_kea_subnet`, `opnsense_unbound_host_override`. They remain in
the JSON for reference; trim them when the next provider-pin bump
forces a regeneration.
