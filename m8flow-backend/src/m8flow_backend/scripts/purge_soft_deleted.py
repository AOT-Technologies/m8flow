"""CLI script to permanently purge soft-deleted process models and groups past retention."""
from __future__ import annotations

import argparse
import logging
import sys

from m8flow_backend import config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Purge soft-deleted process models/groups older than retention period."
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override M8FLOW_SOFT_DELETE_RETENTION_DAYS (default: env or 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be purged without actually deleting.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logger = logging.getLogger("m8flow.purge_soft_deleted")

    retention_days = args.retention_days if args.retention_days is not None else config.soft_delete_retention_days()
    retention_seconds = retention_days * 86400

    logger.info("Starting purge with retention_days=%d dry_run=%s", retention_days, args.dry_run)

    from m8flow_backend.app import create_app

    app = create_app()
    with app.app_context():
        from m8flow_backend.services.soft_delete_service import SoftDeleteService

        summary = SoftDeleteService.purge_expired(retention_seconds, dry_run=args.dry_run)

    logger.info("Purge complete: %s", summary)
    if summary.get("errors"):
        logger.error("Errors during purge: %s", summary["errors"])
        sys.exit(1)


if __name__ == "__main__":
    main()
