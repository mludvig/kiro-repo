"""Main entry point for the Debian Repository Manager Lambda function."""

from typing import Any

from src.aws_permissions import AWSPermissionValidator, validate_iam_role_authentication
from src.config import (
    ENV_AWS_REGION,
    ENV_DYNAMODB_TABLE,
    ENV_S3_BUCKET,
    get_env_var,
    setup_logging,
)
from src.metadata_client import MetadataClient
from src.notification_service import NotificationService
from src.package_downloader import PackageDownloader
from src.repository_builder import RepositoryBuilder
from src.s3_publisher import S3Publisher
from src.version_manager import VersionManager


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda handler function.

    Supports manual rebuild via event parameter:
    - force_rebuild: Set to true to rebuild repository from DynamoDB without checking for new versions

    Example invocation:
        aws lambda invoke --function-name debian-repo-manager \\
            --payload '{"force_rebuild": true}' response.json

    Args:
        event: Lambda event data (supports "force_rebuild" boolean parameter)
        context: Lambda context object

    Returns:
        Response dictionary with status and message
    """
    # Set up logging
    system_logger = setup_logging()
    logger = system_logger.logger
    operation_logger = system_logger.get_operation_logger()

    try:
        # Check for force rebuild flag
        force_rebuild = event.get("force_rebuild", False)
        if force_rebuild:
            logger.info(
                "Force rebuild requested - will rebuild repository from DynamoDB"
            )

        # Log system startup
        system_logger.log_system_start(
            lambda_request_id=getattr(context, "aws_request_id", "unknown"),
            function_name=getattr(context, "function_name", "unknown"),
            function_version=getattr(context, "function_version", "unknown"),
        )

        # Validate IAM role authentication
        operation_logger.start_operation("iam_validation")
        validate_iam_role_authentication()
        operation_logger.complete_operation("iam_validation", success=True)

        # Get configuration
        s3_bucket = get_env_var(ENV_S3_BUCKET, required=True)
        dynamodb_table = get_env_var(ENV_DYNAMODB_TABLE, required=True)
        region = get_env_var(ENV_AWS_REGION, "us-east-1")

        # Validate all AWS permissions upfront
        operation_logger.start_operation("permission_validation")
        permission_validator = AWSPermissionValidator(region)
        permission_validator.validate_all_permissions(s3_bucket, dynamodb_table)
        operation_logger.complete_operation("permission_validation", success=True)

        # Initialize components (with permission validation disabled since we already validated)
        metadata_client = MetadataClient()
        version_manager = VersionManager(validate_permissions=False)
        package_downloader = PackageDownloader()
        repository_builder = RepositoryBuilder()
        s3_publisher = S3Publisher(validate_permissions=False)
        notification_service = NotificationService(validate_permissions=False)

        # Check for new version and download if needed (skip if force rebuild)
        local_files_map = {}
        current_release = None

        if not force_rebuild:
            # Normal workflow: check for new versions
            operation_logger.start_operation("metadata_fetch")
            current_release = metadata_client.get_current_release()
            operation_logger.complete_operation(
                "metadata_fetch", success=True, version=current_release.version
            )

            # Check if version is already processed
            operation_logger.start_operation("version_check")
            if version_manager.is_version_processed(current_release.version):
                logger.info(
                    f"Version {current_release.version} already processed, skipping"
                )
                operation_logger.complete_operation(
                    "version_check", success=True, already_processed=True
                )

                system_logger.log_system_termination(success=True)
                return {
                    "statusCode": 200,
                    "body": f"Version {current_release.version} already processed",
                }
            operation_logger.complete_operation(
                "version_check", success=True, already_processed=False
            )

            # Download new version
            operation_logger.start_operation("package_download")
            local_files = package_downloader.download_release_files(current_release)
            package_downloader.verify_package_integrity(local_files)

            # Populate file metadata in the release info
            package_downloader.populate_file_metadata(current_release, local_files)

            operation_logger.complete_operation(
                "package_download", success=True, version=current_release.version
            )

            # Mark version as processed
            operation_logger.start_operation("version_storage")
            version_manager.mark_version_processed(current_release)
            operation_logger.complete_operation("version_storage", success=True)

            # Create a mapping of the current release to its downloaded files
            local_files_map = {current_release.version: local_files}

        # Shared path: Build and upload repository (for both normal and force rebuild)
        operation_logger.start_operation("repository_build")
        all_releases = version_manager.get_all_releases()

        repository_structure = repository_builder.create_repository_structure(
            all_releases, local_files_map, s3_bucket
        )
        operation_logger.complete_operation(
            "repository_build", success=True, total_releases=len(all_releases)
        )

        # Upload to S3
        operation_logger.start_operation("s3_upload")
        s3_publisher.upload_repository(repository_structure)
        operation_logger.complete_operation("s3_upload", success=True)

        # Clean up downloaded files (if any)
        if local_files_map:
            package_downloader.cleanup_all_downloads()

        # Send success notification (only for new version processing)
        if current_release:
            notification_service.send_success_notification(current_release)

        # Log successful completion
        system_logger.increment_metric("operations_completed", 1)
        if current_release:
            system_logger.set_metric(
                "latest_version_processed", current_release.version
            )
        else:
            system_logger.set_metric("rebuild_releases_count", len(all_releases))
        system_logger.log_system_termination(success=True)

        if force_rebuild:
            return {
                "statusCode": 200,
                "body": f"Successfully rebuilt repository with {len(all_releases)} releases",
            }
        else:
            return {
                "statusCode": 200,
                "body": f"Successfully processed version {current_release.version}",
            }

    except Exception as e:
        # Send failure notification
        try:
            notification_service = NotificationService(validate_permissions=False)
            notification_service.send_failure_notification(e, "Lambda execution")
        except Exception as notification_error:
            # If notification fails, just log it - don't fail the entire function
            logger.error(f"Failed to send failure notification: {notification_error}")

        # Log error and system failure
        system_logger.increment_metric("operations_failed", 1)
        operation_logger.log_error("lambda_execution", e)
        system_logger.log_system_termination(success=False)

        return {"statusCode": 500, "body": f"Error processing repository: {str(e)}"}


def main():
    """Local development entry point."""
    import logging

    # Mock Lambda context for local testing
    class MockContext:
        aws_request_id = "local-test"
        function_name = "debian-repo-manager-local"
        function_version = "$LATEST"

    # Mock event
    event = {}
    context = MockContext()

    result = lambda_handler(event, context)
    logger = logging.getLogger(__name__)
    logger.info(f"Result: {result}")


if __name__ == "__main__":
    main()
