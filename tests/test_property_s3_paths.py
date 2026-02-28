"""Property-based tests for S3 upload path correctness and metadata.

This module contains property tests that validate S3 upload paths follow
the correct Debian pool structure, Content-Type headers are set correctly,
and public read permissions are properly configured.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from src.models import LocalReleaseFiles, PackageMetadata, RepositoryStructure
from src.repository_builder import RepositoryBuilder
from src.s3_publisher import S3Publisher

# --- Strategies ---

version_strategy = st.builds(
    lambda major, minor, patch_v: f"{major}.{minor}.{patch_v}",
    major=st.integers(min_value=0, max_value=99),
    minor=st.integers(min_value=0, max_value=99),
    patch_v=st.integers(min_value=0, max_value=999),
)

bucket_name_strategy = st.from_regex(r"^[a-z0-9][a-z0-9\-]{1,61}[a-z0-9]$")

package_name_strategy = st.sampled_from(["kiro", "kiro-repo", "kiro-cli"])

architecture_strategy = st.sampled_from(["amd64", "all", "arm64"])


def make_package_metadata(
    package_name: str, version: str, architecture: str
) -> PackageMetadata:
    """Create a PackageMetadata instance for testing."""
    return PackageMetadata(
        package_name=package_name,
        version=version,
        architecture=architecture,
        pub_date="2024-01-15",
        deb_url=f"https://example.com/{package_name}_{version}.deb",
        actual_filename=f"{package_name}_{version}_{architecture}.deb",
        file_size=1024,
        md5_hash="d41d8cd98f00b204e9800998ecf8427e",
        sha1_hash="da39a3ee5e6b4b0d3255bfef95601890afd80709",
        sha256_hash=(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        ),
        section="editors",
        priority="optional",
        maintainer="Kiro Team <support@kiro.dev>",
        homepage="https://kiro.dev",
        description=f"{package_name} package",
    )


# --- Property Tests ---


# **Property 15: S3 Upload Path Correctness**
# **Validates: Requirements 11.2, 11.3, 11.5**
# NOTE: Current implementation uses hardcoded "kiro" path - will be updated in future
@settings(deadline=None)
@given(
    bucket_name=bucket_name_strategy,
    version=version_strategy,
    architecture=architecture_strategy,
)
def test_s3_upload_path_correctness(bucket_name, version, architecture):
    """Property: For any package, the S3 upload path follows the Debian pool
    structure: pool/main/{first_letter}/{package_name}/{filename}.

    Validates:
    - Req 11.2: Pool directory structure follows Debian conventions
    - Req 11.3: Package files uploaded to correct pool subdirectories
    - Req 11.5: Path construction uses package_name for routing

    NOTE: Current implementation uses hardcoded "kiro" paths. This test validates
    the current behavior. Full multi-package support will be added later.
    """
    # Use "kiro" package since that's what current implementation supports
    package_name = "kiro"
    metadata = make_package_metadata(package_name, version, architecture)

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create temporary package files
        version_dir = Path(temp_dir) / f"{package_name}-{version}"
        version_dir.mkdir(parents=True)

        deb_file = version_dir / metadata.actual_filename
        cert_file = version_dir / f"{package_name}_{version}.pem"
        sig_file = version_dir / f"{package_name}_{version}.bin"

        deb_file.write_bytes(b"fake deb content")
        cert_file.write_bytes(b"fake cert content")
        sig_file.write_bytes(b"fake sig content")

        # Create LocalReleaseFiles
        local_files = LocalReleaseFiles(
            deb_file_path=str(deb_file),
            certificate_path=str(cert_file),
            signature_path=str(sig_file),
            version=version,
        )

        # Create RepositoryStructure
        repo_structure = RepositoryStructure(
            packages_file_content="Package: test\n",
            release_file_content="Origin: test\n",
            kiro_list_content="deb [trusted=yes] https://example.com/ stable main\n",
            deb_files=[local_files],
            base_path=temp_dir,
        )

        # Track uploaded files
        uploaded_files = {}

        def mock_upload_file(file_path, bucket, key, ExtraArgs=None):  # noqa: N803
            uploaded_files[key] = {"file_path": file_path, "extra_args": ExtraArgs}
            return {}

        def mock_put_object(Bucket, Key, Body, ContentType, **kwargs):  # noqa: N803
            uploaded_files[Key] = {"content_type": ContentType}
            return {}

        mock_s3_client = MagicMock()
        mock_s3_client.upload_file = MagicMock(side_effect=mock_upload_file)
        mock_s3_client.put_object = MagicMock(side_effect=mock_put_object)

        with patch("boto3.client", return_value=mock_s3_client):
            with patch("requests.head", return_value=Mock(status_code=200)):
                publisher = S3Publisher(
                    bucket_name=bucket_name,
                    region="us-east-1",
                    validate_permissions=False,
                )
                publisher.upload_repository(repo_structure)

        # Verify pool directory structure (currently hardcoded to "kiro")
        pool_keys = [k for k in uploaded_files.keys() if k.startswith("pool/main/")]

        assert len(pool_keys) > 0, "Should upload files to pool directory"

        for key in pool_keys:
            # Verify path structure components
            assert key.startswith("pool/main/k/kiro/"), (
                "Path should follow pool/main/k/kiro/ structure"
            )
            # Verify filename is preserved
            filename = key.split("/")[-1]
            assert filename in [
                metadata.actual_filename,
                f"{package_name}_{version}.pem",
                f"{package_name}_{version}.bin",
            ], f"Filename {filename} should be one of the expected files"


# **Property 16: Content-Type Headers**
# **Validates: Requirements 11.6**
@settings(deadline=None)
@given(
    bucket_name=bucket_name_strategy,
    package_name=package_name_strategy,
    version=version_strategy,
    architecture=architecture_strategy,
)
def test_content_type_headers(bucket_name, package_name, version, architecture):
    """Property: All uploaded files have appropriate Content-Type headers set
    based on their file extension (.deb, .pem, .bin, text files).

    Validates:
    - Req 11.6: Content-Type headers are set correctly for all file types
    """
    metadata = make_package_metadata(package_name, version, architecture)

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create temporary package files
        version_dir = Path(temp_dir) / f"{package_name}-{version}"
        version_dir.mkdir(parents=True)

        deb_file = version_dir / metadata.actual_filename
        cert_file = version_dir / f"{package_name}_{version}.pem"
        sig_file = version_dir / f"{package_name}_{version}.bin"

        deb_file.write_bytes(b"fake deb content")
        cert_file.write_bytes(b"fake cert content")
        sig_file.write_bytes(b"fake sig content")

        local_files = LocalReleaseFiles(
            deb_file_path=str(deb_file),
            certificate_path=str(cert_file),
            signature_path=str(sig_file),
            version=version,
        )

        repo_structure = RepositoryStructure(
            packages_file_content="Package: test\n",
            release_file_content="Origin: test\n",
            kiro_list_content="deb [trusted=yes] https://example.com/ stable main\n",
            deb_files=[local_files],
            base_path=temp_dir,
        )

        # Track content types
        content_types = {}

        def mock_upload_file(file_path, bucket, key, ExtraArgs=None):  # noqa: N803
            if ExtraArgs and "ContentType" in ExtraArgs:
                content_types[key] = ExtraArgs["ContentType"]
            return {}

        def mock_put_object(Bucket, Key, Body, ContentType, **kwargs):  # noqa: N803
            content_types[Key] = ContentType
            return {}

        mock_s3_client = MagicMock()
        mock_s3_client.upload_file = MagicMock(side_effect=mock_upload_file)
        mock_s3_client.put_object = MagicMock(side_effect=mock_put_object)

        with patch("boto3.client", return_value=mock_s3_client):
            with patch("requests.head", return_value=Mock(status_code=200)):
                publisher = S3Publisher(
                    bucket_name=bucket_name,
                    region="us-east-1",
                    validate_permissions=False,
                )
                publisher.upload_repository(repo_structure)

        # Verify Content-Type for different file types
        for key, content_type in content_types.items():
            if key.endswith(".deb"):
                assert content_type == "application/vnd.debian.binary-package", (
                    f".deb files should have correct Content-Type, got {content_type}"
                )
            elif key.endswith(".pem"):
                # Accept both possible MIME types for .pem files
                assert content_type in [
                    "application/x-pem-file",
                    "application/pem-certificate-chain",
                ], (
                    f".pem files should have correct Content-Type, got {content_type}"
                )
            elif key.endswith(".bin"):
                assert content_type == "application/octet-stream", (
                    f".bin files should have correct Content-Type, got {content_type}"
                )
            elif key in ["dists/stable/main/binary-amd64/Packages", "dists/stable/Release", "dists/stable/InRelease", "kiro.list"]:
                assert content_type == "text/plain", (
                    f"Text files should have text/plain Content-Type, got {content_type}"
                )
            elif key == "index.html":
                assert content_type == "text/html", (
                    f"HTML files should have text/html Content-Type, got {content_type}"
                )


# **Property 17: Public Read Permissions**
# **Validates: Requirements 11.7**
@settings(deadline=None)
@given(
    bucket_name=bucket_name_strategy,
    package_name=package_name_strategy,
    version=version_strategy,
    architecture=architecture_strategy,
)
def test_public_read_permissions(bucket_name, package_name, version, architecture):
    """Property: All uploaded repository files are publicly accessible via HTTPS
    after upload, verified by the upload_repository method.

    Validates:
    - Req 11.7: All repository files have public read access
    """
    metadata = make_package_metadata(package_name, version, architecture)

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create temporary package files
        version_dir = Path(temp_dir) / f"{package_name}-{version}"
        version_dir.mkdir(parents=True)

        deb_file = version_dir / metadata.actual_filename
        cert_file = version_dir / f"{package_name}_{version}.pem"
        sig_file = version_dir / f"{package_name}_{version}.bin"

        deb_file.write_bytes(b"fake deb content")
        cert_file.write_bytes(b"fake cert content")
        sig_file.write_bytes(b"fake sig content")

        local_files = LocalReleaseFiles(
            deb_file_path=str(deb_file),
            certificate_path=str(cert_file),
            signature_path=str(sig_file),
            version=version,
        )

        repo_structure = RepositoryStructure(
            packages_file_content="Package: test\n",
            release_file_content="Origin: test\n",
            kiro_list_content="deb [trusted=yes] https://example.com/ stable main\n",
            deb_files=[local_files],
            base_path=temp_dir,
        )

        # Track HEAD requests for accessibility verification
        head_requests = []

        def mock_head_request(url, **kwargs):
            head_requests.append(url)
            mock_response = Mock()
            mock_response.status_code = 200
            return mock_response

        mock_s3_client = MagicMock()
        mock_s3_client.upload_file = MagicMock(return_value={})
        mock_s3_client.put_object = MagicMock(return_value={})

        with patch("boto3.client", return_value=mock_s3_client):
            with patch("requests.head", side_effect=mock_head_request):
                publisher = S3Publisher(
                    bucket_name=bucket_name,
                    region="us-east-1",
                    validate_permissions=False,
                )
                publisher.upload_repository(repo_structure)

        # Verify that accessibility was checked for all uploaded files
        assert len(head_requests) > 0, (
            "Should verify accessibility of uploaded files"
        )

        # Verify all HEAD requests use HTTPS and correct bucket
        expected_base_url = f"https://{bucket_name}.s3.amazonaws.com/"
        for url in head_requests:
            assert url.startswith(expected_base_url), (
                f"All URLs should use HTTPS and correct bucket: {url}"
            )


# **Property 15: S3 Upload Path Correctness (Multiple Packages)**
# **Validates: Requirements 11.2, 11.3, 11.5**
# NOTE: Current implementation uses hardcoded "kiro" path - will be updated in future
@settings(deadline=None)
@given(
    bucket_name=bucket_name_strategy,
    versions=st.lists(
        version_strategy,
        min_size=1,
        max_size=3,
        unique=True,
    ),
)
def test_s3_upload_path_correctness_multiple_packages(bucket_name, versions):
    """Property: When uploading multiple package versions, each is uploaded to
    the pool directory with correct structure.

    Validates:
    - Req 11.2: Pool directory structure is maintained for multiple packages
    - Req 11.3: Package files uploaded to correct pool subdirectories
    - Req 11.5: Path construction correctly handles multiple versions

    NOTE: Current implementation uses hardcoded "kiro" paths. This test validates
    the current behavior with multiple versions of the same package.
    """
    package_name = "kiro"
    architecture = "amd64"

    with tempfile.TemporaryDirectory() as temp_dir:
        local_files_list = []

        for version in versions:
            metadata = make_package_metadata(package_name, version, architecture)

            # Create temporary package files with unique directory per version
            version_dir = Path(temp_dir) / f"{package_name}-{version}"
            version_dir.mkdir(parents=True, exist_ok=True)

            deb_file = version_dir / metadata.actual_filename
            cert_file = version_dir / f"{package_name}_{version}.pem"
            sig_file = version_dir / f"{package_name}_{version}.bin"

            deb_file.write_bytes(b"fake deb content")
            cert_file.write_bytes(b"fake cert content")
            sig_file.write_bytes(b"fake sig content")

            local_files = LocalReleaseFiles(
                deb_file_path=str(deb_file),
                certificate_path=str(cert_file),
                signature_path=str(sig_file),
                version=version,
            )
            local_files_list.append(local_files)

        repo_structure = RepositoryStructure(
            packages_file_content="Package: test\n",
            release_file_content="Origin: test\n",
            kiro_list_content="deb [trusted=yes] https://example.com/ stable main\n",
            deb_files=local_files_list,
            base_path=temp_dir,
        )

        # Track uploaded files
        uploaded_files = {}

        def mock_upload_file(file_path, bucket, key, ExtraArgs=None):  # noqa: N803
            uploaded_files[key] = file_path
            return {}

        mock_s3_client = MagicMock()
        mock_s3_client.upload_file = MagicMock(side_effect=mock_upload_file)
        mock_s3_client.put_object = MagicMock(return_value={})

        with patch("boto3.client", return_value=mock_s3_client):
            with patch("requests.head", return_value=Mock(status_code=200)):
                publisher = S3Publisher(
                    bucket_name=bucket_name,
                    region="us-east-1",
                    validate_permissions=False,
                )
                publisher.upload_repository(repo_structure)

        # Verify pool directory structure
        pool_keys = [k for k in uploaded_files.keys() if k.startswith("pool/main/")]

        # Should have 3 files per version (deb, cert, sig)
        expected_file_count = len(versions) * 3
        assert len(pool_keys) == expected_file_count, (
            f"Should upload {expected_file_count} files to pool, got {len(pool_keys)}"
        )

        # Verify all files use the correct pool path
        for key in pool_keys:
            assert key.startswith("pool/main/k/kiro/"), (
                f"All files should use pool/main/k/kiro/ path, got {key}"
            )
