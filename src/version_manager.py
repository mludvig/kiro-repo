"""DynamoDB-based version manager for tracking processed package versions."""

import logging
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.aws_permissions import AWSPermissionValidator
from src.config import ENV_AWS_REGION, ENV_DYNAMODB_TABLE, get_env_var
from src.models import ReleaseInfo

logger = logging.getLogger(__name__)


class VersionManager:
    """Manages version tracking and comparison using DynamoDB."""

    def __init__(
        self,
        table_name: str | None = None,
        region: str | None = None,
        validate_permissions: bool = True,
    ):
        """Initialize the version manager.

        Args:
            table_name: DynamoDB table name. If None, uses environment variable.
            region: AWS region. If None, uses environment variable or default.
            validate_permissions: Whether to validate permissions on initialization.
        """
        self.table_name = table_name or get_env_var(ENV_DYNAMODB_TABLE, required=True)
        self.region = region or get_env_var(ENV_AWS_REGION, "us-east-1")

        # Validate permissions before initializing resources
        if validate_permissions:
            permission_validator = AWSPermissionValidator(self.region)
            permission_validator.validate_dynamodb_permissions(
                self.table_name, ["PutItem", "GetItem", "Scan"]
            )

        # Initialize DynamoDB client and table resource
        self.dynamodb = boto3.resource("dynamodb", region_name=self.region)
        self.table = self.dynamodb.Table(self.table_name)

        logger.info(f"Initialized VersionManager with table: {self.table_name}")

    def get_processed_versions(self) -> list[str]:
        """Get list of all processed version numbers.

        Returns:
            List of version strings that have been processed.

        Raises:
            ClientError: If DynamoDB operation fails.
        """
        logger.info("Retrieving all processed versions from DynamoDB")

        try:
            versions = []
            response = self.table.scan(ProjectionExpression="version")

            # Add versions from first page
            versions.extend([item["version"] for item in response.get("Items", [])])

            # Handle pagination
            while "LastEvaluatedKey" in response:
                logger.debug(
                    f"Scanning next page, found {len(versions)} versions so far"
                )
                response = self.table.scan(
                    ProjectionExpression="version",
                    ExclusiveStartKey=response["LastEvaluatedKey"],
                )
                versions.extend([item["version"] for item in response.get("Items", [])])

            logger.info(f"Retrieved {len(versions)} processed versions")
            return versions

        except ClientError as e:
            logger.error(f"Failed to retrieve processed versions: {e}")
            raise

    def is_version_processed(self, version: str) -> bool:
        """Check if a specific version has been processed.

        Args:
            version: Version string to check.

        Returns:
            True if version has been processed, False otherwise.

        Raises:
            ClientError: If DynamoDB operation fails.
        """
        logger.debug(f"Checking if version {version} has been processed")

        try:
            response = self.table.get_item(
                Key={"version": version}, ProjectionExpression="version"
            )

            exists = "Item" in response
            logger.debug(f"Version {version} processed: {exists}")
            return exists

        except ClientError as e:
            logger.error(f"Failed to check version {version}: {e}")
            raise

    def mark_version_processed(self, release_info: ReleaseInfo) -> None:
        """Mark a version as processed by storing its information in DynamoDB.

        Args:
            release_info: Release information to store.

        Raises:
            ClientError: If DynamoDB operation fails.
        """
        logger.info(f"Marking version {release_info.version} as processed")

        # Set processed timestamp if not already set
        if release_info.processed_timestamp is None:
            release_info.processed_timestamp = datetime.utcnow()

        item = {
            "version": release_info.version,
            "deb_url": release_info.deb_url,
            "certificate_url": release_info.certificate_url,
            "signature_url": release_info.signature_url,
            "pub_date": release_info.pub_date,
            "processed_timestamp": release_info.processed_timestamp.isoformat(),
            "notes": release_info.notes,
        }

        # Add file metadata if available
        if release_info.actual_filename is not None:
            item["actual_filename"] = release_info.actual_filename
        if release_info.file_size is not None:
            item["file_size"] = release_info.file_size
        if release_info.md5_hash is not None:
            item["md5_hash"] = release_info.md5_hash
        if release_info.sha1_hash is not None:
            item["sha1_hash"] = release_info.sha1_hash
        if release_info.sha256_hash is not None:
            item["sha256_hash"] = release_info.sha256_hash

        try:
            self.table.put_item(Item=item)
            logger.info(f"Successfully stored version {release_info.version}")

        except ClientError as e:
            logger.error(f"Failed to store version {release_info.version}: {e}")
            raise

    def get_all_releases(self) -> list[ReleaseInfo]:
        """Get all stored release information from DynamoDB.

        Returns:
            List of ReleaseInfo objects for all processed versions.

        Raises:
            ClientError: If DynamoDB operation fails.
        """
        logger.info("Retrieving all release information from DynamoDB")

        try:
            releases = []
            response = self.table.scan()

            # Process first page
            releases.extend(self._items_to_releases(response.get("Items", [])))

            # Handle pagination
            while "LastEvaluatedKey" in response:
                logger.debug(
                    f"Scanning next page, found {len(releases)} releases so far"
                )
                response = self.table.scan(
                    ExclusiveStartKey=response["LastEvaluatedKey"]
                )
                releases.extend(self._items_to_releases(response.get("Items", [])))

            logger.info(f"Retrieved {len(releases)} total releases")
            return releases

        except ClientError as e:
            logger.error(f"Failed to retrieve all releases: {e}")
            raise

    def _items_to_releases(self, items: list[dict[str, Any]]) -> list[ReleaseInfo]:
        """Convert DynamoDB items to ReleaseInfo objects.

        Args:
            items: List of DynamoDB items.

        Returns:
            List of ReleaseInfo objects.
        """
        releases = []

        for item in items:
            try:
                # Parse processed timestamp if present
                processed_timestamp = None
                if "processed_timestamp" in item:
                    processed_timestamp = datetime.fromisoformat(
                        item["processed_timestamp"]
                    )

                release = ReleaseInfo(
                    version=item["version"],
                    pub_date=item["pub_date"],
                    deb_url=item["deb_url"],
                    certificate_url=item["certificate_url"],
                    signature_url=item["signature_url"],
                    notes=item.get("notes", ""),
                    processed_timestamp=processed_timestamp,
                    # File metadata (may be None for older entries)
                    actual_filename=item.get("actual_filename"),
                    file_size=item.get("file_size"),
                    md5_hash=item.get("md5_hash"),
                    sha1_hash=item.get("sha1_hash"),
                    sha256_hash=item.get("sha256_hash"),
                )
                releases.append(release)

            except (KeyError, ValueError) as e:
                logger.warning(
                    f"Skipping invalid item {item.get('version', 'unknown')}: {e}"
                )
                continue

        return releases
