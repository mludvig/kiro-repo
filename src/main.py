"""Main entry point for the Debian Repository Manager Lambda function."""

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.aws_permissions import AWSPermissionValidator, validate_iam_role_authentication
from src.config import (
    ENV_AWS_REGION,
    ENV_DYNAMODB_TABLE,
    ENV_S3_BUCKET,
    get_env_var,
    setup_logging,
)
from src.models import LocalReleaseFiles, PackageMetadata, ReleaseInfo
from src.notification_service import NotificationService
from src.package_router import PackageRouter
from src.repository_builder import RepositoryBuilder
from src.s3_publisher import S3Publisher
from src.utils import parse_version
from src.version_manager import VersionManager


def _extract_filename_from_url(url: str) -> str:
    """Extract filename from URL.

    Args:
        url: URL to extract filename from

    Returns:
        Filename extracted from URL
    """
    parsed_url = urlparse(url)
    filename = Path(parsed_url.path).name
    if not filename:
        if url.endswith(".deb") or "deb" in url:
            filename = "package.deb"
        elif url.endswith(".pem") or "certificate" in url:
            filename = "certificate.pem"
        elif url.endswith(".bin") or "signature" in url:
            filename = "signature.bin"
        else:
            filename = "unknown_file"
    return filename


def _create_local_files_from_metadata(
    metadata: PackageMetadata,
) -> LocalReleaseFiles:
    """Create LocalReleaseFiles from PackageMetadata for kiro packages.

    Args:
        metadata: Package metadata with URLs

    Returns:
        LocalReleaseFiles with constructed paths
    """
    version_dir = f"/tmp/kiro-{metadata.version}"
    deb_filename = metadata.actual_filename
    cert_filename = (
        _extract_filename_from_url(metadata.certificate_url)
        if metadata.certificate_url
        else "certificate.pem"
    )
    sig_filename = (
        _extract_filename_from_url(metadata.signature_url)
        if metadata.signature_url
        else "signature.bin"
    )
    return LocalReleaseFiles(
        deb_file_path=f"{version_dir}/{deb_filename}",
        certificate_path=f"{version_dir}/{cert_filename}",
        signature_path=f"{version_dir}/{sig_filename}",
        version=metadata.version,
    )


def _convert_package_metadata_to_release_info(
    metadata: PackageMetadata,
) -> ReleaseInfo:
    """Convert PackageMetadata to ReleaseInfo for legacy notifications.

    Args:
        metadata: Package metadata

    Returns:
        ReleaseInfo for legacy notification system
    """
    return ReleaseInfo(
        version=metadata.version,
        pub_date=metadata.pub_date,
        deb_url=metadata.deb_url,
        certificate_url=metadata.certificate_url or "",
        signature_url=metadata.signature_url or "",
        notes=metadata.notes or "",
        actual_filename=metadata.actual_filename,
        file_size=metadata.file_size,
        md5_hash=metadata.md5_hash,
        sha1_hash=metadata.sha1_hash,
        sha256_hash=metadata.sha256_hash,
        processed_timestamp=metadata.processed_timestamp,
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda handler function with multi-package support.

    Supports manual rebuild via event parameter:
    - force_rebuild: Set to true to rebuild repository from DynamoDB

    Example invocation:
        aws lambda invoke --function-name debian-repo-manager \\
            --payload '{"force_rebuild": true}' response.json

    Args:
        event: Lambda event data (supports "force_rebuild" boolean parameter)
        context: Lambda context object

    Returns:
        Response dictionary with status and message
    """
    system_logger = setup_logging()
    logger = system_logger.logger
    operation_logger = system_logger.get_operation_logger()

    try:
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

        # Initialize components
        package_router = PackageRouter(validate_permissions=False)
        version_manager = VersionManager(validate_permissions=False)
        repository_builder = RepositoryBuilder()
        s3_publisher = S3Publisher(validate_permissions=False)
        notification_service = NotificationService(validate_permissions=False)

        # Process packages (skip if force rebuild)
        new_packages: list[PackageMetadata] = []
        if not force_rebuild:
            operation_logger.start_operation("package_processing")
            new_packages = package_router.process_all_packages(force_rebuild=False)
            operation_logger.complete_operation(
                "package_processing",
                success=True,
                new_packages_count=len(new_packages),
            )

            if not new_packages:
                logger.info("No new packages to process")
                system_logger.log_system_termination(success=True)
                return {
                    "statusCode": 200,
                    "body": "No new packages to process",
                }

        # Build repository from all packages in DynamoDB
        operation_logger.start_operation("repository_build")
        all_packages = version_manager.get_all_packages()

        # Create local files map for newly downloaded kiro packages
        local_files_map: dict[str, LocalReleaseFiles] = {}
        for pkg in new_packages:
            if pkg.package_name == "kiro":
                local_files_map[pkg.version] = _create_local_files_from_metadata(pkg)

        repository_structure = repository_builder.create_repository_structure(
            packages=all_packages,
            local_files_map=local_files_map,
            bucket_name=s3_bucket,
        )
        operation_logger.complete_operation(
            "repository_build",
            success=True,
            total_packages=len(all_packages),
        )

        # Upload to S3
        operation_logger.start_operation("s3_upload")
        s3_publisher.upload_repository(repository_structure)

        # Upload convenience copy of latest kiro-repo
        kiro_repo_packages = [
            p for p in all_packages if p.package_name == "kiro-repo"
        ]
        if kiro_repo_packages:
            latest_kiro_repo = max(
                kiro_repo_packages,
                key=lambda p: parse_version(p.version),
            )
            s3_publisher.upload_convenience_copy(latest_kiro_repo)

        operation_logger.complete_operation("s3_upload", success=True)

        # Clean up downloaded files
        package_router.cleanup_downloads()

        # Send notifications for new packages
        if new_packages:
            for pkg in new_packages:
                notification_service.send_success_notification(
                    _convert_package_metadata_to_release_info(pkg)
                )

        # Log successful completion
        system_logger.increment_metric("operations_completed", 1)
        system_logger.set_metric("total_packages", len(all_packages))
        system_logger.log_system_termination(success=True)

        if force_rebuild:
            return {
                "statusCode": 200,
                "body": f"Successfully rebuilt repository with {len(all_packages)} packages",
            }
        else:
            return {
                "statusCode": 200,
                "body": f"Successfully processed {len(new_packages)} new packages",
            }

    except Exception as e:
        # Send failure notification
        try:
            notification_service = NotificationService(validate_permissions=False)
            notification_service.send_failure_notification(e, "Lambda execution")
        except Exception as notification_error:
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
