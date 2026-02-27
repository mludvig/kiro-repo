"""Package handler for kiro-repo packages from S3 staging area."""

import logging

import boto3

from src.config import ENV_S3_BUCKET, get_env_var
from src.config_manager import PackageConfig
from src.models import PackageMetadata
from src.package_handlers.base import PackageHandler

logger = logging.getLogger(__name__)


class KiroRepoPackageHandler(PackageHandler):
    """Handles kiro-repo package retrieval from S3 staging area.

    The kiro-repo package is built by an external build script that
    uploads the .deb to an S3 staging area and stores metadata
    directly in DynamoDB. This handler only retrieves the staged
    package file for repository generation.

    Attributes:
        s3_client: Boto3 S3 client for downloading staged packages
        bucket_name: S3 bucket name from environment variable
    """

    def __init__(self, config: PackageConfig) -> None:
        """Initialize the kiro-repo package handler.

        Args:
            config: Package configuration with staging prefix details
        """
        super().__init__(config)

        self.s3_client = boto3.client("s3")
        self.bucket_name = get_env_var(ENV_S3_BUCKET)

    def check_new_version(self) -> str | None:
        """Check for new kiro-repo version.

        Always returns None because kiro-repo packages are triggered
        by the build script, not by version polling.

        Returns:
            None always
        """
        return None

    def acquire_package(self, version: str) -> PackageMetadata:
        """Acquire a kiro-repo package.

        Raises:
            NotImplementedError: Always, because kiro-repo packages
                are stored by the build script directly.
        """
        raise NotImplementedError(
            "kiro-repo packages are stored by build script"
        )

    def get_package_file_path(
        self, metadata: PackageMetadata
    ) -> str:
        """Download package from S3 staging area and return path.

        Downloads the .deb file from the S3 staging area using the
        staging prefix from the package configuration.

        Args:
            metadata: Package metadata identifying the package

        Returns:
            Local filesystem path to the downloaded .deb file
        """
        staging_key = (
            f"{self.config.source.staging_prefix}"
            f"{metadata.actual_filename}"
        )
        local_path = f"/tmp/{metadata.actual_filename}"

        logger.info(
            "Downloading kiro-repo package from S3 staging: %s",
            staging_key,
        )
        self.s3_client.download_file(
            self.bucket_name, staging_key, local_path
        )

        return local_path
