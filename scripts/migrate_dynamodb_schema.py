"""One-time DynamoDB schema migration script.

Transforms existing records from old schema (partition key: version)
to new schema (partition key: package_id = "package_name#version").

Usage:
    python scripts/migrate_dynamodb_schema.py --env dev --dry-run
    python scripts/migrate_dynamodb_schema.py --env dev --backup-file backup.jsonl
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

# Allow imports from src/ when running as a script
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config_manager import ConfigManager, PackageConfig  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Required fields in the new schema
REQUIRED_NEW_FIELDS = {
    "package_id",
    "package_name",
    "version",
    "architecture",
    "section",
    "priority",
    "maintainer",
    "homepage",
    "description",
    "pub_date",
}

# Default values for old kiro records missing new fields
KIRO_DEFAULTS = {
    "package_name": "kiro",
    "architecture": "amd64",
    "section": "editors",
    "priority": "optional",
    "maintainer": "Kiro Team <support@kiro.dev>",
    "homepage": "https://kiro.dev",
    "description": "Kiro IDE - AI-powered development environment",
    "package_type": "external_download",
}


class DynamoDBSchemaMigration:
    """Migrates DynamoDB records from old schema to new multi-package schema.

    Old schema: partition key = "version" (string)
    New schema: partition key = "package_id" = "package_name#version"

    Attributes:
        table_name: DynamoDB table name.
        dry_run: If True, no writes or deletes are performed.
        config_manager: Loads package configs for metadata defaults.
        table: boto3 DynamoDB Table resource.
    """

    def __init__(
        self,
        table_name: str,
        environment: str,
        dry_run: bool = False,
        region: str = "us-east-1",
        config_dir: str = "config/packages",
    ) -> None:
        """Initialise the migration helper.

        Args:
            table_name: Name of the DynamoDB table to migrate.
            environment: Deployment environment label (dev/staging/prod).
            dry_run: When True, skip all write and delete operations.
            region: AWS region for the DynamoDB client.
            config_dir: Path to the package YAML config directory.
        """
        self.table_name = table_name
        self.environment = environment
        self.dry_run = dry_run

        dynamodb = boto3.resource("dynamodb", region_name=region)
        self.table = dynamodb.Table(table_name)

        self.config_manager = ConfigManager(config_dir)
        self._package_configs: dict[str, PackageConfig] = {}
        for cfg in self.config_manager.load_all_configs():
            self._package_configs[cfg.package_name] = cfg

        logger.info(
            "DynamoDBSchemaMigration initialised: table=%s env=%s dry_run=%s",
            table_name,
            environment,
            dry_run,
        )

    # ------------------------------------------------------------------
    # Backup phase
    # ------------------------------------------------------------------

    def backup_existing_records(self, backup_file: Path) -> list[dict[str, Any]]:
        """Scan all records and write them to a JSONL backup file.

        Args:
            backup_file: Destination path for the JSONL backup.

        Returns:
            List of all raw DynamoDB items that were backed up.

        Raises:
            ClientError: If the DynamoDB scan fails.
            IOError: If the backup file cannot be written.
        """
        logger.info("Starting backup of existing DynamoDB records")

        items: list[dict[str, Any]] = []
        try:
            response = self.table.scan()
            items.extend(response.get("Items", []))
            while "LastEvaluatedKey" in response:
                response = self.table.scan(
                    ExclusiveStartKey=response["LastEvaluatedKey"]
                )
                items.extend(response.get("Items", []))
        except ClientError as exc:
            logger.error("DynamoDB scan failed during backup: %s", exc)
            raise

        # Write JSONL
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        with open(backup_file, "w", encoding="utf-8") as fh:
            for item in items:
                fh.write(json.dumps(item, default=str) + "\n")

        # Verify the file was written
        if not backup_file.exists() or backup_file.stat().st_size == 0:
            raise IOError(f"Backup file was not written successfully: {backup_file}")

        logger.info("Backed up %d records to %s", len(items), backup_file)
        return items

    # ------------------------------------------------------------------
    # Transformation phase
    # ------------------------------------------------------------------

    def transform_records(
        self, old_records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Transform old-schema records to new-schema records.

        For each record:
        - Determines package_name (defaults to "kiro" for legacy records)
        - Builds package_id = "package_name#version"
        - Fills in missing Debian metadata fields from PackageConfig or defaults
        - Preserves all existing fields

        Args:
            old_records: Raw DynamoDB items from the old schema.

        Returns:
            List of transformed records ready for the new schema.
            Records that fail validation are skipped with a warning.
        """
        transformed: list[dict[str, Any]] = []

        for record in old_records:
            try:
                new_record = self._transform_single_record(record)
                missing = REQUIRED_NEW_FIELDS - set(new_record.keys())
                if missing:
                    logger.warning(
                        "Skipping record (missing fields %s): %s",
                        missing,
                        record.get("version", record.get("package_id", "unknown")),
                    )
                    continue
                transformed.append(new_record)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Skipping record due to transformation error (%s): %s",
                    exc,
                    record.get("version", record.get("package_id", "unknown")),
                )

        logger.info(
            "Transformed %d / %d records successfully",
            len(transformed),
            len(old_records),
        )
        return transformed

    def _transform_single_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Transform a single DynamoDB record.

        Args:
            record: Raw DynamoDB item.

        Returns:
            Transformed record with new schema fields.
        """
        new_record: dict[str, Any] = dict(record)  # preserve all existing fields

        # Determine package_name
        package_name: str = new_record.get("package_name") or KIRO_DEFAULTS["package_name"]
        new_record["package_name"] = package_name

        # Ensure version is present
        version: str = new_record.get("version", "")
        if not version:
            raise ValueError("Record has no 'version' field")

        # Build package_id if missing or in old format
        new_record["package_id"] = f"{package_name}#{version}"

        # Apply defaults for missing fields
        defaults = self._get_defaults_for_package(package_name)
        for field, default_value in defaults.items():
            if field not in new_record or not new_record[field]:
                new_record[field] = default_value

        # Ensure processed_timestamp is set
        if "processed_timestamp" not in new_record:
            new_record["processed_timestamp"] = datetime.now(timezone.utc).isoformat()

        return new_record

    def _get_defaults_for_package(self, package_name: str) -> dict[str, Any]:
        """Return field defaults for a given package name.

        Prefers values from the loaded PackageConfig; falls back to
        KIRO_DEFAULTS for legacy kiro records.

        Args:
            package_name: Package name to look up.

        Returns:
            Dictionary of field defaults.
        """
        cfg = self._package_configs.get(package_name)
        if cfg:
            return {
                "architecture": cfg.architecture,
                "section": cfg.section,
                "priority": cfg.priority,
                "maintainer": cfg.maintainer,
                "homepage": cfg.homepage,
                "description": cfg.description,
                "package_type": cfg.source.type,
            }
        # Fallback for unknown packages (treat as kiro)
        return KIRO_DEFAULTS.copy()

    # ------------------------------------------------------------------
    # Upload phase
    # ------------------------------------------------------------------

    def upload_new_records(self, new_records: list[dict[str, Any]]) -> None:
        """Write transformed records to DynamoDB using batch writes.

        Skipped entirely when dry_run=True.

        Args:
            new_records: Transformed records to write.

        Raises:
            ClientError: If a batch write fails.
        """
        if self.dry_run:
            logger.info("[dry-run] Would upload %d records (skipped)", len(new_records))
            return

        logger.info("Uploading %d new records to DynamoDB", len(new_records))

        # DynamoDB batch_writer handles chunking into 25-item batches
        with self.table.batch_writer() as batch:
            for idx, record in enumerate(new_records, start=1):
                batch.put_item(Item=record)
                if idx % 10 == 0:
                    logger.info("Uploaded %d / %d records", idx, len(new_records))

        logger.info("Successfully uploaded all %d records", len(new_records))

    # ------------------------------------------------------------------
    # Cleanup phase
    # ------------------------------------------------------------------

    def delete_old_records(self, old_records: list[dict[str, Any]]) -> None:
        """Delete old-schema records from DynamoDB.

        Only deletes records whose primary key is "version" (old schema).
        Records that already have "package_id" as their key are skipped.
        Skipped entirely when dry_run=True.

        Args:
            old_records: Raw DynamoDB items from the backup scan.

        Raises:
            ClientError: If a batch delete fails.
        """
        if self.dry_run:
            logger.info("[dry-run] Would delete old records (skipped)")
            return

        # Identify records that use the old "version" key only
        to_delete = [r for r in old_records if "package_id" not in r and "version" in r]

        if not to_delete:
            logger.info("No old-schema records to delete")
            return

        logger.info("Deleting %d old-schema records", len(to_delete))

        with self.table.batch_writer() as batch:
            for record in to_delete:
                batch.delete_item(Key={"version": record["version"]})

        logger.info("Deleted %d old-schema records", len(to_delete))

    # ------------------------------------------------------------------
    # Dry-run display
    # ------------------------------------------------------------------

    def display_sample_transformations(
        self, old_records: list[dict[str, Any]], sample_size: int = 3
    ) -> None:
        """Print old vs new record formats for the first N records.

        Args:
            old_records: Raw DynamoDB items from the backup scan.
            sample_size: Number of records to display (default 3).
        """
        sample = old_records[:sample_size]
        if not sample:
            print("No records to display.")
            return

        transformed = self.transform_records(sample)
        transformed_by_version = {r["version"]: r for r in transformed}

        print(f"\n{'='*60}")
        print(f"Sample transformations (showing {len(sample)} records)")
        print(f"{'='*60}")

        for old in sample:
            version = old.get("version", "unknown")
            print(f"\n--- Record: version={version} ---")
            print("OLD:")
            print(json.dumps(old, indent=2, default=str))
            new = transformed_by_version.get(version)
            if new:
                print("NEW:")
                print(json.dumps(new, indent=2, default=str))
            else:
                print("NEW: (transformation failed - record would be skipped)")

        print(f"\n{'='*60}\n")


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Migrate DynamoDB records from old schema to new multi-package schema.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry-run: show sample transformations without modifying DynamoDB
  python scripts/migrate_dynamodb_schema.py --env dev --dry-run

  # Actual migration with mandatory backup file
  python scripts/migrate_dynamodb_schema.py --env dev --backup-file backup_20260302.jsonl
""",
    )
    parser.add_argument(
        "--env",
        required=True,
        choices=["dev", "staging", "prod"],
        help="Deployment environment",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show transformations without modifying DynamoDB",
    )
    parser.add_argument(
        "--backup-file",
        type=Path,
        default=None,
        help="Path for the JSONL backup file (required for actual migration)",
    )
    parser.add_argument(
        "--table-name",
        default=None,
        help="Override DynamoDB table name (default: kiro-debian-repo-manager-versions-{env})",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region (default: us-east-1)",
    )
    parser.add_argument(
        "--config-dir",
        default="config/packages",
        help="Path to package YAML config directory (default: config/packages)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the migration script.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Exit code: 0 on success, 1 on failure.
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    # Validate: backup-file is required for actual migration
    if not args.dry_run and args.backup_file is None:
        parser.error("--backup-file is required when not using --dry-run")

    table_name = args.table_name or f"kiro-debian-repo-manager-versions-{args.env}"

    migration = DynamoDBSchemaMigration(
        table_name=table_name,
        environment=args.env,
        dry_run=args.dry_run,
        region=args.region,
        config_dir=args.config_dir,
    )

    backup_file: Path | None = args.backup_file
    old_records: list[dict[str, Any]] = []

    try:
        # Step 1: Backup
        if backup_file:
            old_records = migration.backup_existing_records(backup_file)
        else:
            # dry-run without backup file: scan without writing
            logger.info("[dry-run] Scanning records (no backup file specified)")
            response = migration.table.scan()
            old_records = list(response.get("Items", []))
            while "LastEvaluatedKey" in response:
                response = migration.table.scan(
                    ExclusiveStartKey=response["LastEvaluatedKey"]
                )
                old_records.extend(response.get("Items", []))
            logger.info("[dry-run] Found %d records", len(old_records))

        # Step 2: Show sample transformations in dry-run mode
        if args.dry_run:
            migration.display_sample_transformations(old_records)
            logger.info("[dry-run] Migration preview complete. No changes made.")
            return 0

        # Step 3: Transform
        new_records = migration.transform_records(old_records)
        if not new_records:
            logger.warning("No records were successfully transformed. Aborting.")
            return 1

        # Step 4: Upload new records
        migration.upload_new_records(new_records)

        # Step 5: Delete old records
        migration.delete_old_records(old_records)

        logger.info("Migration complete. %d records migrated.", len(new_records))
        return 0

    except Exception as exc:  # noqa: BLE001
        logger.error("Migration failed: %s", exc)
        if backup_file and backup_file.exists():
            logger.info("Backup preserved at: %s", backup_file)
        return 1


if __name__ == "__main__":
    sys.exit(main())
