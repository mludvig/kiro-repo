"""AWS permissions validation and security utilities."""

import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class AWSPermissionError(Exception):
    """Custom exception for AWS permission-related errors."""

    def __init__(self, service: str, operation: str, error_code: str, message: str):
        self.service = service
        self.operation = operation
        self.error_code = error_code
        super().__init__(message)


class AWSPermissionValidator:
    """Validates AWS permissions before performing operations."""

    def __init__(self, region: str = "us-east-1"):
        """Initialize the permission validator.

        Args:
            region: AWS region for service clients
        """
        self.region = region
        self._clients: dict[str, Any] = {}

    def _get_client(self, service_name: str) -> Any:
        """Get or create AWS service client.

        Args:
            service_name: AWS service name (e.g., 's3', 'dynamodb')

        Returns:
            AWS service client

        Raises:
            AWSPermissionError: If client creation fails due to credentials
        """
        if service_name not in self._clients:
            try:
                self._clients[service_name] = boto3.client(
                    service_name, region_name=self.region
                )
                logger.debug(f"Created {service_name} client for region {self.region}")
            except NoCredentialsError as e:
                error_msg = (
                    f"No AWS credentials found for {service_name}. "
                    "Ensure IAM role is properly configured."
                )
                logger.error(error_msg)
                raise AWSPermissionError(
                    service=service_name,
                    operation="client_creation",
                    error_code="NoCredentials",
                    message=error_msg,
                ) from e
            except Exception as e:
                error_msg = f"Failed to create {service_name} client: {str(e)}"
                logger.error(error_msg)
                raise AWSPermissionError(
                    service=service_name,
                    operation="client_creation",
                    error_code="ClientCreationFailed",
                    message=error_msg,
                ) from e

        return self._clients[service_name]

    def validate_s3_permissions(
        self, bucket_name: str, required_operations: list[str]
    ) -> None:
        """Validate S3 permissions for required operations.

        Args:
            bucket_name: S3 bucket name
            required_operations: List of required operations (e.g., ['GetObject', 'PutObject'])

        Raises:
            AWSPermissionError: If permission validation fails
        """
        logger.info(f"Validating S3 permissions for bucket: {bucket_name}")

        s3_client = self._get_client("s3")

        # Test basic bucket access
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            logger.debug(f"Successfully accessed bucket: {bucket_name}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchBucket":
                error_msg = f"S3 bucket '{bucket_name}' does not exist"
            elif error_code == "Forbidden":
                error_msg = f"Access denied to S3 bucket '{bucket_name}'. Check IAM permissions."
            else:
                error_msg = f"Failed to access S3 bucket '{bucket_name}': {error_code}"

            logger.error(error_msg)
            raise AWSPermissionError(
                service="s3",
                operation="head_bucket",
                error_code=error_code,
                message=error_msg,
            ) from e

        # Test specific operations if requested
        for operation in required_operations:
            self._test_s3_operation(s3_client, bucket_name, operation)

    def _test_s3_operation(
        self, s3_client: Any, bucket_name: str, operation: str
    ) -> None:
        """Test a specific S3 operation permission.

        Args:
            s3_client: S3 client instance
            bucket_name: S3 bucket name
            operation: Operation to test

        Raises:
            AWSPermissionError: If operation is not permitted
        """
        test_key = "permission-test/test-object"

        try:
            if operation == "PutObject":
                # Test put object permission
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=test_key,
                    Body=b"permission test",
                    ACL="public-read",
                )
                logger.debug(f"S3 PutObject permission validated for {bucket_name}")

                # Clean up test object
                try:
                    s3_client.delete_object(Bucket=bucket_name, Key=test_key)
                except ClientError:
                    logger.warning(f"Failed to clean up test object: {test_key}")

            elif operation == "GetObject":
                # Test get object permission (this will fail if object doesn't exist,
                # but we can distinguish between permission and existence errors)
                try:
                    s3_client.get_object(Bucket=bucket_name, Key=test_key)
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    if error_code == "NoSuchKey":
                        # This is expected - we have permission but object doesn't exist
                        logger.debug(
                            f"S3 GetObject permission validated for {bucket_name}"
                        )
                    elif error_code in ["Forbidden", "AccessDenied"]:
                        raise  # Re-raise permission error
                    else:
                        logger.debug(
                            f"S3 GetObject permission validated for {bucket_name}"
                        )

            elif operation == "ListBucket":
                # Test list bucket permission
                s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
                logger.debug(f"S3 ListBucket permission validated for {bucket_name}")

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "Forbidden" or error_code == "AccessDenied":
                error_msg = (
                    f"Access denied for S3 {operation} on bucket '{bucket_name}'. "
                    "Check IAM role permissions."
                )
            else:
                error_msg = f"S3 {operation} validation failed for bucket '{bucket_name}': {error_code}"

            logger.error(error_msg)
            raise AWSPermissionError(
                service="s3",
                operation=operation,
                error_code=error_code,
                message=error_msg,
            ) from e

    def validate_dynamodb_permissions(
        self, table_name: str, required_operations: list[str]
    ) -> None:
        """Validate DynamoDB permissions for required operations.

        Args:
            table_name: DynamoDB table name
            required_operations: List of required operations (e.g., ['GetItem', 'PutItem'])

        Raises:
            AWSPermissionError: If permission validation fails
        """
        logger.info(f"Validating DynamoDB permissions for table: {table_name}")

        dynamodb_client = self._get_client("dynamodb")

        # Test basic table access
        try:
            response = dynamodb_client.describe_table(TableName=table_name)
            table_status = response["Table"]["TableStatus"]
            logger.debug(
                f"Successfully accessed table: {table_name} (status: {table_status})"
            )

            if table_status != "ACTIVE":
                error_msg = f"DynamoDB table '{table_name}' is not active (status: {table_status})"
                logger.error(error_msg)
                raise AWSPermissionError(
                    service="dynamodb",
                    operation="describe_table",
                    error_code="TableNotActive",
                    message=error_msg,
                )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "ResourceNotFoundException":
                error_msg = f"DynamoDB table '{table_name}' does not exist"
            elif error_code == "AccessDeniedException":
                error_msg = f"Access denied to DynamoDB table '{table_name}'. Check IAM permissions."
            else:
                error_msg = (
                    f"Failed to access DynamoDB table '{table_name}': {error_code}"
                )

            logger.error(error_msg)
            raise AWSPermissionError(
                service="dynamodb",
                operation="describe_table",
                error_code=error_code,
                message=error_msg,
            ) from e

        # Test specific operations if requested
        for operation in required_operations:
            self._test_dynamodb_operation(dynamodb_client, table_name, operation)

    def _test_dynamodb_operation(
        self, dynamodb_client: Any, table_name: str, operation: str
    ) -> None:
        """Test a specific DynamoDB operation permission.

        Args:
            dynamodb_client: DynamoDB client instance
            table_name: DynamoDB table name
            operation: Operation to test

        Raises:
            AWSPermissionError: If operation is not permitted
        """
        test_key = {"version": {"S": "permission-test-key"}}

        try:
            if operation == "PutItem":
                # Test put item permission
                dynamodb_client.put_item(
                    TableName=table_name,
                    Item={
                        **test_key,
                        "test_field": {"S": "permission test"},
                    },
                )
                logger.debug(f"DynamoDB PutItem permission validated for {table_name}")

                # Clean up test item
                try:
                    dynamodb_client.delete_item(TableName=table_name, Key=test_key)
                except ClientError:
                    logger.warning(f"Failed to clean up test item from {table_name}")

            elif operation == "GetItem":
                # Test get item permission
                try:
                    dynamodb_client.get_item(TableName=table_name, Key=test_key)
                    logger.debug(
                        f"DynamoDB GetItem permission validated for {table_name}"
                    )
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "Unknown")
                    if error_code != "AccessDeniedException":
                        # Any error other than access denied means we have permission
                        logger.debug(
                            f"DynamoDB GetItem permission validated for {table_name}"
                        )
                    else:
                        raise

            elif operation == "Scan":
                # Test scan permission
                dynamodb_client.scan(TableName=table_name, Limit=1)
                logger.debug(f"DynamoDB Scan permission validated for {table_name}")

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "AccessDeniedException":
                error_msg = (
                    f"Access denied for DynamoDB {operation} on table '{table_name}'. "
                    "Check IAM role permissions."
                )
            else:
                error_msg = f"DynamoDB {operation} validation failed for table '{table_name}': {error_code}"

            logger.error(error_msg)
            raise AWSPermissionError(
                service="dynamodb",
                operation=operation,
                error_code=error_code,
                message=error_msg,
            ) from e

    def validate_all_permissions(self, s3_bucket: str, dynamodb_table: str) -> None:
        """Validate all required AWS permissions for the application.

        Args:
            s3_bucket: S3 bucket name
            dynamodb_table: DynamoDB table name

        Raises:
            AWSPermissionError: If any permission validation fails
        """
        logger.info("Validating all AWS permissions")

        # Validate S3 permissions
        required_s3_operations = ["PutObject", "GetObject", "ListBucket"]
        self.validate_s3_permissions(s3_bucket, required_s3_operations)

        # Validate DynamoDB permissions
        required_dynamodb_operations = ["PutItem", "GetItem", "Scan"]
        self.validate_dynamodb_permissions(dynamodb_table, required_dynamodb_operations)

        logger.info("All AWS permissions validated successfully")


def validate_iam_role_authentication() -> None:
    """Validate that IAM role-based authentication is properly configured.

    Raises:
        AWSPermissionError: If IAM role authentication is not properly configured
    """
    logger.info("Validating IAM role-based authentication")

    try:
        # Get current identity using STS
        sts_client = boto3.client("sts")
        identity = sts_client.get_caller_identity()

        # Check if we're using a role (not user credentials)
        arn = identity.get("Arn", "")
        if ":assumed-role/" not in arn and ":role/" not in arn:
            error_msg = (
                f"Not using IAM role authentication. Current identity: {arn}. "
                "Lambda functions should use IAM roles, not user credentials."
            )
            logger.error(error_msg)
            raise AWSPermissionError(
                service="sts",
                operation="get_caller_identity",
                error_code="NotUsingRole",
                message=error_msg,
            )

        logger.info(f"IAM role authentication validated. Using role: {arn}")

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_msg = f"Failed to validate IAM role authentication: {error_code}"
        logger.error(error_msg)
        raise AWSPermissionError(
            service="sts",
            operation="get_caller_identity",
            error_code=error_code,
            message=error_msg,
        ) from e
    except NoCredentialsError as e:
        error_msg = (
            "No AWS credentials found. Ensure Lambda function has an IAM role attached."
        )
        logger.error(error_msg)
        raise AWSPermissionError(
            service="sts",
            operation="get_caller_identity",
            error_code="NoCredentials",
            message=error_msg,
        ) from e
