"""SNS notification service for the Debian Repository Manager."""

import boto3
from botocore.exceptions import ClientError

from src.config import get_env_var
from src.models import ReleaseInfo


class NotificationService:
    """Service for sending SNS notifications about repository operations."""

    def __init__(self, validate_permissions: bool = True):
        """Initialize the notification service.

        Args:
            validate_permissions: Whether to validate SNS permissions on init
        """
        self.region = get_env_var("AWS_REGION", "us-east-1")
        self.success_topic_arn = get_env_var("SUCCESS_SNS_TOPIC")
        self.failure_topic_arn = get_env_var("FAILURE_SNS_TOPIC")

        # Only create SNS client if topics are configured
        self.sns_client = None
        if self.success_topic_arn or self.failure_topic_arn:
            self.sns_client = boto3.client("sns", region_name=self.region)

            if validate_permissions:
                self._validate_permissions()

    def _validate_permissions(self) -> None:
        """Validate SNS publish permissions."""
        if not self.sns_client:
            return

        try:
            # Test permissions by getting topic attributes
            if self.success_topic_arn:
                self.sns_client.get_topic_attributes(TopicArn=self.success_topic_arn)
            if self.failure_topic_arn:
                self.sns_client.get_topic_attributes(TopicArn=self.failure_topic_arn)
        except ClientError as e:
            raise RuntimeError(f"SNS permission validation failed: {e}")

    def send_success_notification(
        self, release: ReleaseInfo, message: str = None
    ) -> None:
        """Send a success notification.

        Args:
            release: The release that was processed
            message: Optional custom message
        """
        if not self.sns_client or not self.success_topic_arn:
            return

        subject = f"Kiro Debian Repository Updated - Version {release.version}"

        if message is None:
            message = (
                f"Successfully processed Kiro IDE version {release.version}\n\n"
                f"Release Details:\n"
                f"- Version: {release.version}\n"
                f"- Architecture: amd64\n"
                f"- Download URL: {release.deb_url}\n"
                f"- Published: {release.pub_date}\n\n"
                f"The Debian repository has been updated and is available for installation."
            )

        try:
            self.sns_client.publish(
                TopicArn=self.success_topic_arn, Subject=subject, Message=message
            )
        except ClientError as e:
            # Log error but don't fail the entire operation
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send success notification: {e}")

    def send_failure_notification(self, error: Exception, context: str = None) -> None:
        """Send a failure notification.

        Args:
            error: The exception that occurred
            context: Optional context about where the error occurred
        """
        if not self.sns_client or not self.failure_topic_arn:
            return

        subject = "Kiro Debian Repository Manager - Processing Failed"

        message = "The Kiro Debian Repository Manager encountered an error:\n\n"

        if context:
            message += f"Context: {context}\n\n"

        message += (
            f"Error Type: {type(error).__name__}\n"
            f"Error Message: {str(error)}\n\n"
            f"Please check the CloudWatch logs for more details."
        )

        try:
            self.sns_client.publish(
                TopicArn=self.failure_topic_arn, Subject=subject, Message=message
            )
        except ClientError as e:
            # Log error but don't fail the entire operation
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send failure notification: {e}")

    def send_no_update_notification(self, current_version: str) -> None:
        """Send a notification when no update is needed.

        Args:
            current_version: The version that was already processed
        """
        if not self.sns_client or not self.success_topic_arn:
            return

        subject = "Kiro Debian Repository - No Update Needed"

        message = (
            f"The Kiro Debian Repository Manager ran successfully but found no new versions to process.\n\n"
            f"Current Version: {current_version}\n\n"
            f"The repository is up to date."
        )

        try:
            self.sns_client.publish(
                TopicArn=self.success_topic_arn, Subject=subject, Message=message
            )
        except ClientError as e:
            # Log error but don't fail the entire operation
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send no-update notification: {e}")
