"""S3 publisher for uploading debian repository files."""

import logging
import mimetypes
import time
from pathlib import Path

import boto3
import requests
from botocore.exceptions import BotoCoreError, ClientError

from src.aws_permissions import AWSPermissionValidator
from src.config import ENV_AWS_REGION, ENV_S3_BUCKET, get_env_var
from src.models import RepositoryStructure

logger = logging.getLogger(__name__)


class S3Publisher:
    """Handles uploading repository files to S3 with proper permissions."""

    def __init__(
        self,
        bucket_name: str | None = None,
        region: str | None = None,
        validate_permissions: bool = True,
    ):
        """Initialize S3Publisher.

        Args:
            bucket_name: S3 bucket name. If None, reads from environment.
            region: AWS region. If None, reads from environment.
            validate_permissions: Whether to validate permissions on initialization.
        """
        self.bucket_name = bucket_name or get_env_var(ENV_S3_BUCKET, required=True)
        self.region = region or get_env_var(ENV_AWS_REGION, default="us-east-1")

        # Validate permissions before initializing resources
        if validate_permissions:
            permission_validator = AWSPermissionValidator(self.region)
            permission_validator.validate_s3_permissions(
                self.bucket_name, ["PutObject", "GetObject", "ListBucket"]
            )

        # Initialize S3 client
        self.s3_client = boto3.client("s3", region_name=self.region)

        logger.info(f"Initialized S3Publisher for bucket: {self.bucket_name}")

    def upload_repository(self, repo_structure: RepositoryStructure) -> None:
        """Upload repository structure to S3.

        Args:
            repo_structure: The repository structure to upload

        Raises:
            ClientError: If S3 operations fail
            ValueError: If upload verification fails
        """
        logger.info("Starting repository upload to S3")
        uploaded_keys = []

        try:
            # Upload Packages file
            packages_key = "dists/stable/main/binary-amd64/Packages"
            self._upload_content(
                packages_key,
                repo_structure.packages_file_content,
                content_type="text/plain",
            )
            uploaded_keys.append(packages_key)

            # Upload Release file
            release_key = "dists/stable/Release"
            self._upload_content(
                release_key,
                repo_structure.release_file_content,
                content_type="text/plain",
            )
            uploaded_keys.append(release_key)

            # Upload all deb files and associated files
            for local_files in repo_structure.deb_files:
                # Upload .deb file
                deb_key = f"pool/main/k/kiro/{Path(local_files.deb_file_path).name}"
                self._upload_file(local_files.deb_file_path, deb_key)
                uploaded_keys.append(deb_key)

                # Upload certificate file
                cert_key = f"pool/main/k/kiro/{Path(local_files.certificate_path).name}"
                self._upload_file(local_files.certificate_path, cert_key)
                uploaded_keys.append(cert_key)

                # Upload signature file
                sig_key = f"pool/main/k/kiro/{Path(local_files.signature_path).name}"
                self._upload_file(local_files.signature_path, sig_key)
                uploaded_keys.append(sig_key)

            # Set public read permissions on all uploaded files
            self.set_public_permissions(uploaded_keys)

            # Verify upload success
            if not self.verify_upload_success(uploaded_keys):
                raise ValueError("Upload verification failed")

            logger.info(f"Successfully uploaded {len(uploaded_keys)} files to S3")

        except Exception as e:
            logger.error(f"Failed to upload repository to S3: {e}")
            raise

    def _upload_content(
        self, key: str, content: str, content_type: str = "text/plain"
    ) -> None:
        """Upload string content to S3 with retry logic.

        Args:
            key: S3 object key
            content: Content to upload
            content_type: MIME content type

        Raises:
            ClientError: If all upload attempts fail
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.debug(
                    f"Uploading content to s3://{self.bucket_name}/{key} (attempt {attempt + 1})"
                )

                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=key,
                    Body=content.encode("utf-8"),
                    ContentType=content_type,
                )

                logger.debug(f"Successfully uploaded content to {key}")
                return

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "Unknown")
                logger.warning(
                    f"Upload attempt {attempt + 1} failed for {key}: {error_code}"
                )

                if attempt == max_retries - 1:
                    logger.error(f"All upload attempts failed for {key}")
                    raise

                # Exponential backoff
                time.sleep(2**attempt)

    def _upload_file(self, file_path: str, key: str) -> None:
        """Upload file to S3 with retry logic.

        Args:
            file_path: Local file path
            key: S3 object key

        Raises:
            ClientError: If all upload attempts fail
            FileNotFoundError: If local file doesn't exist
        """
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Determine content type
        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            if file_path.endswith(".deb"):
                content_type = "application/vnd.debian.binary-package"
            elif file_path.endswith(".pem"):
                content_type = "application/x-pem-file"
            elif file_path.endswith(".bin"):
                content_type = "application/octet-stream"
            else:
                content_type = "application/octet-stream"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.debug(
                    f"Uploading file {file_path} to s3://{self.bucket_name}/{key} (attempt {attempt + 1})"
                )

                self.s3_client.upload_file(
                    file_path,
                    self.bucket_name,
                    key,
                    ExtraArgs={"ContentType": content_type},
                )

                logger.debug(f"Successfully uploaded file {file_path} to {key}")
                return

            except (ClientError, BotoCoreError) as e:
                logger.warning(
                    f"Upload attempt {attempt + 1} failed for {file_path}: {e}"
                )

                if attempt == max_retries - 1:
                    logger.error(f"All upload attempts failed for {file_path}")
                    raise

                # Exponential backoff
                time.sleep(2**attempt)

    def set_public_permissions(self, s3_keys: list[str]) -> None:
        """Set public read permissions on S3 objects.
        
        Note: Public access is handled by bucket policy, so this method
        just logs that permissions are managed at the bucket level.

        Args:
            s3_keys: List of S3 object keys
        """
        logger.info(
            f"Public read access for {len(s3_keys)} objects is managed by bucket policy"
        )

    def verify_upload_success(self, s3_keys: list[str]) -> bool:
        """Verify that all uploaded files are accessible via HTTPS.

        Args:
            s3_keys: List of S3 object keys to verify

        Returns:
            True if all files are accessible, False otherwise
        """
        logger.info(f"Verifying accessibility of {len(s3_keys)} uploaded files")

        for key in s3_keys:
            # Construct public URL
            url = f"https://{self.bucket_name}.s3.amazonaws.com/{key}"

            try:
                # Make HEAD request to check accessibility
                response = requests.head(url, timeout=10)
                if response.status_code != 200:
                    logger.error(
                        f"File not accessible: {url} (status: {response.status_code})"
                    )
                    return False

                logger.debug(f"Verified accessibility: {url}")

            except requests.RequestException as e:
                logger.error(f"Failed to verify accessibility of {url}: {e}")
                return False

        logger.info("All uploaded files are accessible")
        return True
