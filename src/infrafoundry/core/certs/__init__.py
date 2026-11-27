"""Per-device Let's Encrypt certificates over ACME with Cloudflare DNS-01 (ADR-0040).

``schema`` checks the declaration, ``issuer`` orders a certificate, ``store`` keeps it in a
package's SOPS ``secrets.yaml``, ``install`` and ``ssh_installer`` put it on a device, and
``service`` ties them together for ``foundry certs``. Only ``acme_client`` imports the
``acme`` library. Nothing here logs or returns key material or tokens.
"""
