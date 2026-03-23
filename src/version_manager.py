"""DynamoDB-based version manager for tracking processed package versions."""

import logging
import time
from datetime import datetime
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1  # seconds, doubled each attempt

from src.aws_permissions import AWSPermissionValidator
from src.config import ENV_AWS_REGION, ENV_DYNAMODB_TABLE, get_env_var
from src.models import PackageMetadata, ReleaseInfo
from src.utils import parse_version

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

    def _retry_dynamodb(self, operation_name: str, fn: Any) -> Any:
        """Execute a DynamoDB operation with exponential backoff retry.

        Args:
            operation_name: Human-readable name for logging.
            fn: Zero-argument callable that performs the DynamoDB operation.

        Returns:
            The return value of fn().

        Raises:
            ClientError: If all retry attempts fail.
        """
        for attempt in range(_MAX_RETRIES):
            try:
                return fn()
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        "DynamoDB %s failed (attempt %d/%d, code=%s), "
                        "retrying in %.1fs",
                        operation_name,
                        attempt + 1,
                        _MAX_RETRIES,
                        error_code,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "DynamoDB %s failed after %d attempts (code=%s)",
                        operation_name,
                        _MAX_RETRIES,
                        error_code,
                    )
                    raise

    def get_all_packages(self) -> list[PackageMetadata]:
        """Get all stored package metadata from DynamoDB.

        Returns:
            List of PackageMetadata objects for all packages.

        Raises:
            ClientError: If DynamoDB operation fails.
        """
        logger.info("Retrieving all package metadata from DynamoDB")

        try:
            packages = []
            response = self._retry_dynamodb("scan", lambda: self.table.scan())

            # Process first page
            packages.extend(self._items_to_packages(response.get("Items", [])))

            # Handle pagination
            while "LastEvaluatedKey" in response:
                last_key = response["LastEvaluatedKey"]
                logger.debug(
                    f"Scanning next page, found {len(packages)} packages so far"
                )
                response = self._retry_dynamodb(
                    "scan (paginated)",
                    lambda: self.table.scan(ExclusiveStartKey=last_key),
                )
                packages.extend(self._items_to_packages(response.get("Items", [])))

            logger.info(f"Retrieved {len(packages)} total packages")
            return packages

        except ClientError as e:
            logger.error(f"Failed to retrieve all packages: {e}")
            raise

    def get_packages_by_name(self, package_name: str) -> list[PackageMetadata]:
        """Get all versions of a specific package from DynamoDB.

        Args:
            package_name: Name of the package to retrieve (e.g., "kiro", "kiro-repo").

        Returns:
            List of PackageMetadata objects for the specified package.

        Raises:
            ClientError: If DynamoDB operation fails.
        """
        logger.info(
            f"Retrieving all versions of package '{package_name}' from DynamoDB"
        )

        try:
            packages = []
            filter_expr = Attr("package_name").eq(package_name)
            response = self._retry_dynamodb(
                f"scan (package={package_name})",
                lambda: self.table.scan(FilterExpression=filter_expr),
            )

            # Process first page
            packages.extend(self._items_to_packages(response.get("Items", [])))

            # Handle pagination
            while "LastEvaluatedKey" in response:
                last_key = response["LastEvaluatedKey"]
                logger.debug(
                    f"Scanning next page, found {len(packages)} packages so far"
                )
                response = self._retry_dynamodb(
                    f"scan paginated (package={package_name})",
                    lambda: self.table.scan(
                        FilterExpression=filter_expr,
                        ExclusiveStartKey=last_key,
                    ),
                )
                packages.extend(self._items_to_packages(response.get("Items", [])))

            logger.info(
                f"Retrieved {len(packages)} versions of package '{package_name}'"
            )
            return packages

        except ClientError as e:
            logger.error(f"Failed to retrieve packages for '{package_name}': {e}")
            raise

    def get_latest_package(self, package_name: str) -> PackageMetadata | None:
        """Get the latest version of a specific package from DynamoDB.

        Retrieves all versions of the package and returns the one with the
        highest semantic version using parse_version for comparison.

        Args:
            package_name: Name of the package (e.g., "kiro", "kiro-repo").

        Returns:
            PackageMetadata for the latest version, or None if no packages found.

        Raises:
            ClientError: If DynamoDB operation fails.
        """
        logger.info(f"Retrieving latest version of package '{package_name}'")

        packages = self.get_packages_by_name(package_name)

        if not packages:
            logger.info(f"No packages found for '{package_name}'")
            return None

        latest = max(packages, key=lambda p: parse_version(p.version))
        logger.info(
            f"Latest version of '{package_name}' is {latest.version}"
        )
        return latest

    def store_package_metadata(self, metadata: PackageMetadata) -> None:
        """Store package metadata in DynamoDB.

        Args:
            metadata: Package metadata to store.

        Raises:
            ClientError: If DynamoDB operation fails.
        """
        logger.info(
            f"Storing metadata for {metadata.package_name} version {metadata.version}"
        )

        # Set processed timestamp if not already set
        if metadata.processed_timestamp is None:
            metadata.processed_timestamp = datetime.utcnow()

        item = {
            "package_id": metadata.package_id,
            "package_name": metadata.package_name,
            "version": metadata.version,
            "architecture": metadata.architecture,
            "pub_date": metadata.pub_date,
            "deb_url": metadata.deb_url,
            "actual_filename": metadata.actual_filename,
            "file_size": metadata.file_size,
            "md5_hash": metadata.md5_hash,
            "sha1_hash": metadata.sha1_hash,
            "sha256_hash": metadata.sha256_hash,
            "processed_timestamp": metadata.processed_timestamp.isoformat(),
            "section": metadata.section,
            "priority": metadata.priority,
            "maintainer": metadata.maintainer,
            "homepage": metadata.homepage,
            "description": metadata.description,
        }

        # Add optional fields if present
        if metadata.certificate_url is not None:
            item["certificate_url"] = metadata.certificate_url
        if metadata.signature_url is not None:
            item["signature_url"] = metadata.signature_url
        if metadata.notes is not None:
            item["notes"] = metadata.notes
        if metadata.depends is not None:
            item["depends"] = metadata.depends

        try:
            self._retry_dynamodb(
                f"put_item ({metadata.package_name}#{metadata.version})",
                lambda: self.table.put_item(Item=item),
            )
            logger.info(
                f"Successfully stored {metadata.package_name} version {metadata.version}"
            )

        except ClientError as e:
            logger.error(
                f"Failed to store {metadata.package_name} version {metadata.version}: {e}"
            )
            raise

    def is_package_version_processed(self, package_name: str, version: str) -> bool:
        """Check if a specific package version has been processed.

        Args:
            package_name: Name of the package (e.g., "kiro", "kiro-repo").
            version: Version string to check.

        Returns:
            True if package version has been processed, False otherwise.

        Raises:
            ClientError: If DynamoDB operation fails.
        """
        package_id = f"{package_name}#{version}"
        logger.debug(f"Checking if package {package_id} has been processed")

        try:
            response = self._retry_dynamodb(
                f"get_item ({package_id})",
                lambda: self.table.get_item(
                    Key={"package_id": package_id},
                    ProjectionExpression="package_id",
                ),
            )

            exists = "Item" in response
            logger.debug(f"Package {package_id} processed: {exists}")
            return exists

        except ClientError as e:
            logger.error(f"Failed to check package {package_id}: {e}")
            raise

    def _items_to_packages(self, items: list[dict[str, Any]]) -> list[PackageMetadata]:
        """Convert DynamoDB items to PackageMetadata objects.

        Args:
            items: List of DynamoDB items.

        Returns:
            List of PackageMetadata objects. Items with missing required fields
            are skipped and logged as warnings.
        """
        # Required fields that must be present for a valid package entry
        _REQUIRED_FIELDS = {"version", "pub_date", "deb_url"}

        packages = []

        for item in items:
            item_id = item.get("package_id", item.get("version", "unknown"))

            # Check for missing required fields before attempting construction
            missing = _REQUIRED_FIELDS - item.keys()
            if missing:
                logger.warning(
                    "Skipping package '%s': missing required field(s): %s",
                    item_id,
                    ", ".join(sorted(missing)),
                )
                continue

            # Warn about empty/falsy file metadata that may affect repository integrity
            incomplete_fields = [
                f
                for f in ("actual_filename", "sha256_hash", "md5_hash", "sha1_hash")
                if not item.get(f)
            ]
            if incomplete_fields:
                logger.warning(
                    "Package '%s' has incomplete file metadata (field(s) empty: %s) "
                    "— repository entry may be incomplete",
                    item_id,
                    ", ".join(incomplete_fields),
                )

            try:
                # Parse processed timestamp if present
                processed_timestamp = None
                if "processed_timestamp" in item:
                    processed_timestamp = datetime.fromisoformat(
                        item["processed_timestamp"]
                    )

                # Backward compatibility: if package_name is missing, assume "kiro"
                package_name = item.get("package_name", "kiro")

                package = PackageMetadata(
                    package_name=package_name,
                    version=item["version"],
                    architecture=item.get("architecture", "amd64"),
                    pub_date=item["pub_date"],
                    deb_url=item["deb_url"],
                    actual_filename=item.get("actual_filename", ""),
                    file_size=item.get("file_size", 0),
                    md5_hash=item.get("md5_hash", ""),
                    sha1_hash=item.get("sha1_hash", ""),
                    sha256_hash=item.get("sha256_hash", ""),
                    certificate_url=item.get("certificate_url"),
                    signature_url=item.get("signature_url"),
                    notes=item.get("notes"),
                    processed_timestamp=processed_timestamp,
                    section=item.get("section", "editors"),
                    priority=item.get("priority", "optional"),
                    maintainer=item.get("maintainer", "Kiro Team <support@kiro.dev>"),
                    homepage=item.get("homepage", "https://kiro.dev"),
                    description=item.get("description", ""),
                    depends=item.get("depends"),
                )
                packages.append(package)

            except (KeyError, ValueError) as e:
                logger.warning(
                    "Skipping package '%s' due to conversion error: %s",
                    item_id,
                    e,
                )
                continue

        return packages

    # Legacy methods for backward compatibility with ReleaseInfo

    def get_processed_versions(self) -> list[str]:
        """Get list of all processed version numbers (legacy method).

        This method is maintained for backward compatibility. New code should use
        get_all_packages() instead.

        Returns:
            List of version strings that have been processed.

        Raises:
            ClientError: If DynamoDB operation fails.
        """
        logger.info("Retrieving all processed versions from DynamoDB")

        try:
            versions = []
            response = self._retry_dynamodb(
                "scan (versions)",
                lambda: self.table.scan(ProjectionExpression="version"),
            )

            # Add versions from first page
            versions.extend([item["version"] for item in response.get("Items", [])])

            # Handle pagination
            while "LastEvaluatedKey" in response:
                last_key = response["LastEvaluatedKey"]
                logger.debug(
                    f"Scanning next page, found {len(versions)} versions so far"
                )
                response = self._retry_dynamodb(
                    "scan paginated (versions)",
                    lambda: self.table.scan(
                        ProjectionExpression="version",
                        ExclusiveStartKey=last_key,
                    ),
                )
                versions.extend([item["version"] for item in response.get("Items", [])])

            logger.info(f"Retrieved {len(versions)} processed versions")
            return versions

        except ClientError as e:
            logger.error(f"Failed to retrieve processed versions: {e}")
            raise

    def is_version_processed(self, version: str) -> bool:
        """Check if a specific version has been processed (legacy method).

        This method is maintained for backward compatibility. New code should use
        is_package_version_processed() instead.

        Args:
            version: Version string to check.

        Returns:
            True if version has been processed, False otherwise.

        Raises:
            ClientError: If DynamoDB operation fails.
        """
        # For backward compatibility, assume "kiro" package
        return self.is_package_version_processed("kiro", version)

    def mark_version_processed(self, release_info: ReleaseInfo) -> None:
        """Mark a version as processed by storing its information in DynamoDB (legacy method).

        This method is maintained for backward compatibility. New code should use
        store_package_metadata() instead.

        Args:
            release_info: Release information to store.

        Raises:
            ClientError: If DynamoDB operation fails.
        """
        logger.info(f"Marking version {release_info.version} as processed")

        # Set processed timestamp if not already set
        if release_info.processed_timestamp is None:
            release_info.processed_timestamp = datetime.utcnow()

        # Convert ReleaseInfo to PackageMetadata for storage
        metadata = PackageMetadata(
            package_name="kiro",
            version=release_info.version,
            architecture="amd64",
            pub_date=release_info.pub_date,
            deb_url=release_info.deb_url,
            actual_filename=release_info.actual_filename or "",
            file_size=release_info.file_size or 0,
            md5_hash=release_info.md5_hash or "",
            sha1_hash=release_info.sha1_hash or "",
            sha256_hash=release_info.sha256_hash or "",
            certificate_url=release_info.certificate_url,
            signature_url=release_info.signature_url,
            notes=release_info.notes,
            processed_timestamp=release_info.processed_timestamp,
            section="editors",
            priority="optional",
            maintainer="Kiro Team <support@kiro.dev>",
            homepage="https://kiro.dev",
            description="Kiro IDE - AI-powered development environment",
        )

        self.store_package_metadata(metadata)

    def get_all_releases(self) -> list[ReleaseInfo]:
        """Get all stored release information from DynamoDB (legacy method).

        This method is maintained for backward compatibility. New code should use
        get_all_packages() instead.

        Returns:
            List of ReleaseInfo objects for all processed versions.

        Raises:
            ClientError: If DynamoDB operation fails.
        """
        logger.info("Retrieving all release information from DynamoDB (legacy method)")

        try:
            releases = []
            response = self._retry_dynamodb("scan (releases)", lambda: self.table.scan())

            # Process first page
            releases.extend(self._items_to_releases(response.get("Items", [])))

            # Handle pagination
            while "LastEvaluatedKey" in response:
                last_key = response["LastEvaluatedKey"]
                logger.debug(
                    f"Scanning next page, found {len(releases)} releases so far"
                )
                response = self._retry_dynamodb(
                    "scan paginated (releases)",
                    lambda: self.table.scan(ExclusiveStartKey=last_key),
                )
                releases.extend(self._items_to_releases(response.get("Items", [])))

            logger.info(f"Retrieved {len(releases)} total releases")
            return releases

        except ClientError as e:
            logger.error(f"Failed to retrieve all releases: {e}")
            raise

    def _items_to_releases(self, items: list[dict[str, Any]]) -> list[ReleaseInfo]:
        """Convert DynamoDB items to ReleaseInfo objects (legacy method).

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
                    certificate_url=item.get("certificate_url", ""),
                    signature_url=item.get("signature_url", ""),
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
