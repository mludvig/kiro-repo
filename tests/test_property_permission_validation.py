"""Property-based test for AWS permission validation."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, NoCredentialsError
from hypothesis import given
from hypothesis import strategies as st

from src.aws_permissions import (
    AWSPermissionError,
    AWSPermissionValidator,
    validate_iam_role_authentication,
)


# **Feature: debian-repo-manager, Property 10: Permission Validation**
# **Validates: Requirements 7.3**
@given(
    bucket_name=st.text(
        min_size=3,
        max_size=63,
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    ).filter(lambda x: not x.startswith("-") and not x.endswith("-") and "--" not in x),
    table_name=st.text(
        min_size=3,
        max_size=255,
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-",
    ).filter(lambda x: x[0].isalpha() or x[0] == "_"),
    region=st.sampled_from(["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]),
)
def test_permission_validation_property(bucket_name, table_name, region):
    """Property test: For any AWS resource access attempt, the system should validate permissions before performing operations.

    This property tests that the permission validation system correctly checks
    AWS permissions before attempting operations and provides clear error messages
    when permissions are insufficient.
    """
    # Test 1: Successful permission validation
    with patch("boto3.client") as mock_boto_client:
        # Mock successful S3 client
        mock_s3_client = MagicMock()
        mock_s3_client.head_bucket.return_value = {}
        mock_s3_client.put_object.return_value = {}
        mock_s3_client.delete_object.return_value = {}
        mock_s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}}, "GetObject"
        )
        mock_s3_client.list_objects_v2.return_value = {"Contents": []}

        # Mock successful DynamoDB client
        mock_dynamodb_client = MagicMock()
        mock_dynamodb_client.describe_table.return_value = {
            "Table": {"TableStatus": "ACTIVE"}
        }
        mock_dynamodb_client.put_item.return_value = {}
        mock_dynamodb_client.delete_item.return_value = {}
        mock_dynamodb_client.get_item.return_value = {}
        mock_dynamodb_client.scan.return_value = {"Items": []}

        def mock_client_factory(service_name, **kwargs):
            if service_name == "s3":
                return mock_s3_client
            elif service_name == "dynamodb":
                return mock_dynamodb_client
            else:
                return MagicMock()

        mock_boto_client.side_effect = mock_client_factory

        # Create validator and test successful validation
        validator = AWSPermissionValidator(region)

        # Should not raise any exceptions
        validator.validate_s3_permissions(
            bucket_name, ["PutObject", "GetObject", "ListBucket"]
        )
        validator.validate_dynamodb_permissions(
            table_name, ["PutItem", "GetItem", "Scan"]
        )
        validator.validate_all_permissions(bucket_name, table_name)

        # Verify that clients were created with correct region
        assert any(
            call[1].get("region_name") == region
            for call in mock_boto_client.call_args_list
        )


@given(
    bucket_name=st.text(
        min_size=3,
        max_size=63,
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    ).filter(lambda x: not x.startswith("-") and not x.endswith("-") and "--" not in x),
    error_code=st.sampled_from(["Forbidden", "AccessDenied", "NoSuchBucket"]),
    operation=st.sampled_from(["PutObject", "GetObject", "ListBucket"]),
)
def test_s3_permission_error_handling(bucket_name, error_code, operation):
    """Property test: S3 permission errors should be properly caught and converted to clear error messages."""
    with patch("boto3.client") as mock_boto_client:
        mock_s3_client = MagicMock()

        # Configure mock to raise ClientError for the specific operation
        client_error = ClientError({"Error": {"Code": error_code}}, operation)

        # For head_bucket errors, configure the head_bucket call to fail
        if error_code == "NoSuchBucket":
            mock_s3_client.head_bucket.side_effect = client_error
        else:
            # For permission errors, allow head_bucket but fail on specific operations
            mock_s3_client.head_bucket.return_value = {}
            if operation == "PutObject":
                mock_s3_client.put_object.side_effect = client_error
                mock_s3_client.delete_object.return_value = {}  # Allow cleanup
            elif operation == "GetObject":
                mock_s3_client.get_object.side_effect = client_error
            elif operation == "ListBucket":
                mock_s3_client.list_objects_v2.side_effect = client_error

        mock_boto_client.return_value = mock_s3_client

        validator = AWSPermissionValidator()

        # Should raise AWSPermissionError with clear message
        with pytest.raises(AWSPermissionError) as exc_info:
            validator.validate_s3_permissions(bucket_name, [operation])

        error = exc_info.value
        assert error.service == "s3"
        assert error.error_code == error_code
        assert bucket_name in error.args[0]  # Error message should contain bucket name

        # Error message should be clear and actionable
        error_message = error.args[0].lower()
        if error_code in ["Forbidden", "AccessDenied"]:
            assert "access denied" in error_message or "check iam" in error_message
        elif error_code == "NoSuchBucket":
            assert "does not exist" in error_message


@given(
    table_name=st.text(
        min_size=3,
        max_size=255,
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-",
    ).filter(lambda x: x[0].isalpha() or x[0] == "_"),
    error_code=st.sampled_from(["AccessDeniedException", "ResourceNotFoundException"]),
    operation=st.sampled_from(["PutItem", "GetItem", "Scan"]),
)
def test_dynamodb_permission_error_handling(table_name, error_code, operation):
    """Property test: DynamoDB permission errors should be properly caught and converted to clear error messages."""
    with patch("boto3.client") as mock_boto_client:
        mock_dynamodb_client = MagicMock()

        # Configure mock to raise ClientError for the specific operation
        client_error = ClientError({"Error": {"Code": error_code}}, operation)

        # For table not found errors, configure describe_table to fail
        if error_code == "ResourceNotFoundException":
            mock_dynamodb_client.describe_table.side_effect = client_error
        else:
            # For permission errors, allow describe_table but fail on specific operations
            mock_dynamodb_client.describe_table.return_value = {
                "Table": {"TableStatus": "ACTIVE"}
            }
            if operation == "PutItem":
                mock_dynamodb_client.put_item.side_effect = client_error
                mock_dynamodb_client.delete_item.return_value = {}  # Allow cleanup
            elif operation == "GetItem":
                mock_dynamodb_client.get_item.side_effect = client_error
            elif operation == "Scan":
                mock_dynamodb_client.scan.side_effect = client_error

        mock_boto_client.return_value = mock_dynamodb_client

        validator = AWSPermissionValidator()

        # Should raise AWSPermissionError with clear message
        with pytest.raises(AWSPermissionError) as exc_info:
            validator.validate_dynamodb_permissions(table_name, [operation])

        error = exc_info.value
        assert error.service == "dynamodb"
        assert error.error_code == error_code
        assert table_name in error.args[0]  # Error message should contain table name

        # Error message should be clear and actionable
        error_message = error.args[0].lower()
        if error_code == "AccessDeniedException":
            assert "access denied" in error_message or "check iam" in error_message
        elif error_code == "ResourceNotFoundException":
            assert "does not exist" in error_message


@given(
    arn_type=st.sampled_from(["user", "role"]),
    account_id=st.text(
        min_size=12, max_size=12, alphabet="0123456789"
    ),  # AWS account IDs are 12 digits
    resource_name=st.text(
        min_size=1,
        max_size=64,
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
    ).filter(lambda x: x and not x.startswith("-") and not x.endswith("-")),
)
def test_iam_role_authentication_validation(arn_type, account_id, resource_name):
    """Property test: IAM role authentication should be properly validated."""
    with patch("boto3.client") as mock_boto_client:
        mock_sts_client = MagicMock()

        # Create ARN based on type
        if arn_type == "role":
            arn = f"arn:aws:sts::{account_id}:assumed-role/{resource_name}/session"
        else:
            arn = f"arn:aws:iam::{account_id}:user/{resource_name}"

        mock_sts_client.get_caller_identity.return_value = {
            "Arn": arn,
            "Account": account_id,
        }

        mock_boto_client.return_value = mock_sts_client

        if arn_type == "role":
            # Should succeed for role ARNs
            validate_iam_role_authentication()
        else:
            # Should fail for user ARNs
            with pytest.raises(AWSPermissionError) as exc_info:
                validate_iam_role_authentication()

            error = exc_info.value
            assert error.service == "sts"
            assert error.error_code == "NotUsingRole"
            assert "not using iam role" in error.args[0].lower()
            assert arn in error.args[0]


def test_no_credentials_error_handling():
    """Test that NoCredentialsError is properly handled."""
    with patch("boto3.client") as mock_boto_client:
        mock_boto_client.side_effect = NoCredentialsError()

        validator = AWSPermissionValidator()

        with pytest.raises(AWSPermissionError) as exc_info:
            validator.validate_s3_permissions("test-bucket", ["PutObject"])

        error = exc_info.value
        assert error.service == "s3"
        assert error.error_code == "NoCredentials"
        assert "no aws credentials" in error.args[0].lower()
        assert "iam role" in error.args[0].lower()


@given(
    table_status=st.sampled_from(["CREATING", "UPDATING", "DELETING", "ACTIVE"]),
    table_name=st.text(
        min_size=3,
        max_size=255,
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-",
    ).filter(lambda x: x[0].isalpha() or x[0] == "_"),
)
def test_dynamodb_table_status_validation(table_status, table_name):
    """Property test: DynamoDB table status should be validated before operations."""
    with patch("boto3.client") as mock_boto_client:
        mock_dynamodb_client = MagicMock()
        mock_dynamodb_client.describe_table.return_value = {
            "Table": {"TableStatus": table_status}
        }

        mock_boto_client.return_value = mock_dynamodb_client

        validator = AWSPermissionValidator()

        if table_status == "ACTIVE":
            # Should succeed for active tables
            # Mock the operation methods to avoid further calls
            mock_dynamodb_client.put_item.return_value = {}
            mock_dynamodb_client.delete_item.return_value = {}
            mock_dynamodb_client.get_item.return_value = {}
            mock_dynamodb_client.scan.return_value = {"Items": []}

            validator.validate_dynamodb_permissions(table_name, ["PutItem"])
        else:
            # Should fail for non-active tables
            with pytest.raises(AWSPermissionError) as exc_info:
                validator.validate_dynamodb_permissions(table_name, ["PutItem"])

            error = exc_info.value
            assert error.service == "dynamodb"
            assert error.error_code == "TableNotActive"
            assert table_name in error.args[0]
            assert table_status in error.args[0]


@given(
    operations=st.lists(
        st.sampled_from(["PutObject", "GetObject", "ListBucket"]),
        min_size=1,
        max_size=3,
        unique=True,
    ),
    bucket_name=st.text(
        min_size=3,
        max_size=63,
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    ).filter(lambda x: not x.startswith("-") and not x.endswith("-") and "--" not in x),
)
def test_multiple_operations_validation(operations, bucket_name):
    """Property test: Multiple operations should be validated correctly."""
    with patch("boto3.client") as mock_boto_client:
        mock_s3_client = MagicMock()
        mock_s3_client.head_bucket.return_value = {}

        # Configure successful responses for all operations
        mock_s3_client.put_object.return_value = {}
        mock_s3_client.delete_object.return_value = {}
        mock_s3_client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey"}}, "GetObject"
        )  # Expected for non-existent test object
        mock_s3_client.list_objects_v2.return_value = {"Contents": []}

        mock_boto_client.return_value = mock_s3_client

        validator = AWSPermissionValidator()

        # Should validate all operations successfully
        validator.validate_s3_permissions(bucket_name, operations)

        # Verify that each operation was tested
        for operation in operations:
            if operation == "PutObject":
                mock_s3_client.put_object.assert_called()
            elif operation == "GetObject":
                mock_s3_client.get_object.assert_called()
            elif operation == "ListBucket":
                mock_s3_client.list_objects_v2.assert_called()
