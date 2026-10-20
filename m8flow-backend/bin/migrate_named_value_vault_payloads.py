"""Run the manual configuration-variable Vault payload migration."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from m8flow_backend.app import app
    from m8flow_backend.services.named_value_vault_migration import (
        migrate_legacy_named_value_documents,
    )

    with app.app_context(), app.test_request_context("/"):
        result = migrate_legacy_named_value_documents(dry_run=args.dry_run)

    print(
        "Named-value Vault migration complete: "
        f"migrated={result.migrated}, normalized={result.normalized}, "
        f"missing={result.missing_legacy_value}, conflicts={result.conflicts}, "
        f"failures={result.failures}."
    )
    return 1 if result.conflicts or result.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
