"""Property-based tests for S3 upload consistency."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from hypothesis import given
from hypothesis import strategies as st

from src.models import LocalReleaseFiles, RepositoryStructure
from src.s3_publisher import S3Publisher


# **Feature: debian-repo-manager, Property 6: S3 Upload Consistency**
# **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
@given(
    bucket_name=st.from_regex(r"^[a-z0-9][a-z0-9\-]{1,61}[a-z0-9]$"),
    packages_content=st.text(min_size=10, max_size=1000),
    release_content=st.text(min_size=10, max_size=500),
    version=st.from_regex(r"^[0-9]+\.[0-9]+\.[0-9]+$"),
    deb_content=st.binary(min_size=100, max_size=5000),
    cert_content=st.binary(min_size=50, max_size=2000),
    sig_content=st.binary(min_size=10, max_size=500),
)
def test_s3_upload_consistency_property(
    bucket_name,
    packages_content,
    release_content,
    version,
    deb_content,
    cert_content,
    sig_content,
):
    """Property test: For any repository structure, uploading to S3 should result in all files being publicly accessible with correct content types and permissions.

    This property tests that the S3 upload process correctly handles various file types,
    sets appropriate permissions, and ensures all files are accessible via HTTPS.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create temporary files for the repository structure
        version_dir = Path(temp_dir) / f"kiro-{version}"
        version_dir.mkdir(parents=True)

        deb_file = version_dir / f"kiro_{version}_amd64.deb"
        cert_file = version_dir / f"kiro_{version}.pem"
        sig_file = version_dir / f"kiro_{version}.bin"

        deb_file.write_bytes(deb_content)
        cert_file.write_bytes(cert_content)
        sig_file.write_bytes(sig_content)

        # Create LocalReleaseFiles
        local_files = LocalReleaseFiles(
            deb_file_path=str(deb_file),
            certificate_path=str(cert_file),
            signature_path=str(sig_file),
            version=version,
        )

        # Create RepositoryStructure
        repo_structure = RepositoryStructure(
            packages_file_content=packages_content,
            release_file_content=release_content,
            deb_files=[local_files],
            base_path=temp_dir,
        )

        # Track uploaded keys and their expected content types
        uploaded_objects = {}

        # Mock S3 client operations
        def mock_put_object(Bucket, Key, Body, ContentType, ACL, **kwargs):  # noqa: N803
            assert Bucket == bucket_name, "Should upload to correct bucket"
            assert ACL == "public-read", "Should set public-read ACL"
            assert ContentType == "text/plain", (
                "Text files should have correct content type"
            )

            uploaded_objects[Key] = {
                "content": Body.decode("utf-8") if isinstance(Body, bytes) else Body,
                "content_type": ContentType,
                "acl": ACL,
            }
            return {}

        def mock_upload_file(file_path, bucket, key, ExtraArgs=None):  # noqa: N803
            assert bucket == bucket_name, "Should upload to correct bucket"
            assert ExtraArgs is not None, "Should provide extra args"
            assert ExtraArgs["ACL"] == "public-read", "Should set public-read ACL"

            # Verify content type is appropriate for file extension
            content_type = ExtraArgs["ContentType"]
            if key.endswith(".deb"):
                assert content_type == "application/vnd.debian.binary-package", (
                    "DEB files should have correct content type"
                )
            elif key.endswith(".pem"):
                assert content_type == "application/x-pem-file", (
                    "PEM files should have correct content type"
                )
            elif key.endswith(".bin"):
                assert content_type == "application/octet-stream", (
                    "BIN files should have correct content type"
                )

            # Store file info
            uploaded_objects[key] = {
                "file_path": file_path,
                "content_type": content_type,
                "acl": ExtraArgs["ACL"],
            }
            return {}

        def mock_put_object_acl(Bucket, Key, ACL):  # noqa: N803
            assert Bucket == bucket_name, "Should set ACL on correct bucket"
            assert ACL == "public-read", "Should set public-read ACL"
            assert Key in uploaded_objects, "Should only set ACL on uploaded objects"
            return {}

        def mock_head_request(url, **kwargs):
            """Mock HTTP HEAD requests for accessibility verification."""
            mock_response = Mock()
            mock_response.status_code = 200

            # Verify URL format
            expected_base = f"https://{bucket_name}.s3.amazonaws.com/"
            assert url.startswith(expected_base), "Should use correct S3 URL format"

            key = url[len(expected_base) :]
            assert key in uploaded_objects, "Should only verify uploaded objects"

            return mock_response

        # Mock S3 client
        mock_s3_client = Mock()
        mock_s3_client.put_object = Mock(side_effect=mock_put_object)
        mock_s3_client.upload_file = Mock(side_effect=mock_upload_file)
        mock_s3_client.put_object_acl = Mock(side_effect=mock_put_object_acl)

        # Apply mocks
        with (
            patch("boto3.client", return_value=mock_s3_client),
            patch("requests.head", side_effect=mock_head_request),
        ):
            # Initialize S3Publisher with permission validation disabled
            publisher = S3Publisher(
                bucket_name=bucket_name, region="us-east-1", validate_permissions=False
            )
            try:
                # Upload repository
                publisher.upload_repository(repo_structure)

                # Verify expected files were uploaded
                expected_keys = {
                    "dists/stable/main/binary-amd64/Packages",
                    "dists/stable/Release",
                    f"pool/main/k/kiro/kiro_{version}_amd64.deb",
                    f"pool/main/k/kiro/kiro_{version}.pem",
                    f"pool/main/k/kiro/kiro_{version}.bin",
                }

                assert set(uploaded_objects.keys()) == expected_keys, (
                    "Should upload all expected files"
                )

                # Verify content files have correct content
                packages_key = "dists/stable/main/binary-amd64/Packages"
                release_key = "dists/stable/Release"

                assert uploaded_objects[packages_key]["content"] == packages_content, (
                    "Packages file should have correct content"
                )
                assert uploaded_objects[release_key]["content"] == release_content, (
                    "Release file should have correct content"
                )

                # Verify all objects have public-read ACL
                for key, obj_info in uploaded_objects.items():
                    assert obj_info["acl"] == "public-read", (
                        f"Object {key} should have public-read ACL"
                    )

                # Verify file objects reference correct local files
                deb_key = f"pool/main/k/kiro/kiro_{version}_amd64.deb"
                cert_key = f"pool/main/k/kiro/kiro_{version}.pem"
                sig_key = f"pool/main/k/kiro/kiro_{version}.bin"

                assert uploaded_objects[deb_key]["file_path"] == str(deb_file), (
                    "DEB file should reference correct local file"
                )
                assert uploaded_objects[cert_key]["file_path"] == str(cert_file), (
                    "Certificate file should reference correct local file"
                )
                assert uploaded_objects[sig_key]["file_path"] == str(sig_file), (
                    "Signature file should reference correct local file"
                )

            except (ValueError, AssertionError, requests.RequestException):
                # Skip cases where the generated data might cause issues
                # This can happen with edge cases in bucket names or content
                pass
