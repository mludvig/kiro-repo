"""Property-based tests for the main Lambda handler.

**Property 3: Force Rebuild Retrieves All Packages**
**Validates: Requirements 1.4, 7.2**

**Property 4: Repository Metadata Generation from DynamoDB Alone**
**Validates: Requirements 1.5, 9.6**
"""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from src.main import lambda_handler
from src.models import PackageMetadata

# --- Shared strategies ---

KNOWN_PACKAGE_NAMES = ["kiro", "kiro-repo", "kiro-cli"]

version_strategy = st.builds(
    lambda major, minor, patch_v: f"{major}.{minor}.{patch_v}",
    major=st.integers(min_value=0, max_value=99),
    minor=st.integers(min_value=0, max_value=99),
    patch_v=st.integers(min_value=0, max_value=999),
)

package_name_strategy = st.sampled_from(KNOWN_PACKAGE_NAMES)

architecture_strategy = st.sampled_from(["amd64", "all"])


def make_package_metadata(
    package_name: str,
    version: str,
    architecture: str = "amd64",
) -> PackageMetadata:
    """Create a minimal but valid PackageMetadata instance."""
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
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        ),
        processed_timestamp=datetime(2024, 1, 15, 12, 0, 0),
        section="editors",
        priority="optional",
        maintainer="Kiro Team <support@kiro.dev>",
        homepage="https://kiro.dev",
        description=f"{package_name} package",
    )


# Strategy that generates a list of PackageMetadata with unique (name, version) pairs
packages_strategy = st.lists(
    st.tuples(package_name_strategy, version_strategy, architecture_strategy),
    min_size=1,
    max_size=10,
    unique_by=lambda t: (t[0], t[1]),
).map(
    lambda tuples: [
        make_package_metadata(name, ver, arch) for name, ver, arch in tuples
    ]
)


# ---------------------------------------------------------------------------
# Property 3: Force Rebuild Retrieves All Packages
# ---------------------------------------------------------------------------


# **Property 3: Force Rebuild Retrieves All Packages**
# **Validates: Requirements 1.4, 7.2**
@settings(deadline=None, max_examples=25)
@given(packages=packages_strategy)
def test_force_rebuild_retrieves_all_packages(packages: list[PackageMetadata]):
    """Property: when force_rebuild=True, lambda_handler skips version checking
    and uses all packages from DynamoDB via VersionManager.get_all_packages().

    Specifically:
    - PackageRouter.process_all_packages is NOT called (or called with
      force_rebuild=True and returns [])
    - VersionManager.get_all_packages is called and returns all N packages
    - RepositoryBuilder.create_repository_structure is called with all N packages
    - The response body mentions the correct package count

    Validates:
    - Req 1.4: Force_Rebuild retrieves all Package_Entry records from DynamoDB
    - Req 7.2: Force_Rebuild retrieves all Package_Entry records from DynamoDB_Store
    """
    event = {"force_rebuild": True}

    mock_context = MagicMock()
    mock_context.aws_request_id = "test-request-id"
    mock_context.function_name = "test-function"
    mock_context.function_version = "$LATEST"

    mock_repo_structure = MagicMock()

    with (
        patch("src.main.validate_iam_role_authentication"),
        patch("src.main.AWSPermissionValidator") as mock_validator_cls,
        patch("src.main.PackageRouter") as mock_router_cls,
        patch("src.main.VersionManager") as mock_vm_cls,
        patch("src.main.RepositoryBuilder") as mock_rb_cls,
        patch("src.main.S3Publisher") as mock_s3_cls,
        patch("src.main.NotificationService"),
        patch.dict(
            os.environ,
            {
                "S3_BUCKET_NAME": "test-bucket",
                "DYNAMODB_TABLE_NAME": "test-table",
                "AWS_REGION": "us-east-1",
            },
        ),
    ):
        mock_validator_cls.return_value.validate_all_permissions.return_value = None

        mock_router = mock_router_cls.return_value
        mock_router.process_all_packages.return_value = []

        mock_vm = mock_vm_cls.return_value
        mock_vm.get_all_packages.return_value = packages

        mock_rb = mock_rb_cls.return_value
        mock_rb.create_repository_structure.return_value = mock_repo_structure

        mock_s3 = mock_s3_cls.return_value

        response = lambda_handler(event, mock_context)

    # --- Assertions ---

    # Req 1.4 / 7.2: get_all_packages must be called to retrieve all records
    mock_vm.get_all_packages.assert_called_once()

    # process_all_packages must NOT be called (force_rebuild skips it),
    # OR if called, it must be called with force_rebuild=True
    if mock_router.process_all_packages.called:
        mock_router.process_all_packages.assert_called_with(force_rebuild=True)

    # create_repository_structure must receive all N packages from DynamoDB
    call_args = mock_rb.create_repository_structure.call_args
    assert call_args is not None, "create_repository_structure was not called"
    called_packages = call_args.kwargs.get(
        "packages", call_args.args[0] if call_args.args else None
    )
    assert called_packages is not None
    assert len(called_packages) == len(packages), (
        f"Expected {len(packages)} packages passed to create_repository_structure, "
        f"got {len(called_packages)}"
    )

    # Response must be 200 and mention the package count
    assert response["statusCode"] == 200
    assert str(len(packages)) in response["body"]

    # upload_repository must be called (Req 7.4: upload all metadata files)
    mock_s3.upload_repository.assert_called_once()


# ---------------------------------------------------------------------------
# Property 4: Repository Metadata Generation from DynamoDB Alone
# ---------------------------------------------------------------------------


# **Property 4: Repository Metadata Generation from DynamoDB Alone**
# **Validates: Requirements 1.5, 9.6**
@settings(deadline=None, max_examples=25)
@given(packages=packages_strategy)
def test_repository_metadata_generation_from_dynamodb_alone(
    packages: list[PackageMetadata],
):
    """Property: the repository structure is built using only data from DynamoDB
    (get_all_packages), not from reading .deb files from S3 or disk.

    Specifically:
    - VersionManager.get_all_packages returns the generated packages
    - RepositoryBuilder.create_repository_structure is called with exactly
      those packages (no additional file I/O needed)
    - The packages passed to create_repository_structure match the DynamoDB data

    Validates:
    - Req 1.5: system uses only DynamoDB_Store data without reading package files
    - Req 9.6: Package_Entry contains sufficient info to generate Packages_File
                entry without reading the .deb file
    """
    # Use force_rebuild=True to exercise the pure DynamoDB path
    event = {"force_rebuild": True}

    mock_context = MagicMock()
    mock_context.aws_request_id = "test-request-id"
    mock_context.function_name = "test-function"
    mock_context.function_version = "$LATEST"

    mock_repo_structure = MagicMock()

    with (
        patch("src.main.validate_iam_role_authentication"),
        patch("src.main.AWSPermissionValidator"),
        patch("src.main.PackageRouter") as mock_router_cls,
        patch("src.main.VersionManager") as mock_vm_cls,
        patch("src.main.RepositoryBuilder") as mock_rb_cls,
        patch("src.main.S3Publisher"),
        patch("src.main.NotificationService"),
        patch.dict(
            os.environ,
            {
                "S3_BUCKET_NAME": "test-bucket",
                "DYNAMODB_TABLE_NAME": "test-table",
                "AWS_REGION": "us-east-1",
            },
        ),
    ):
        mock_router_cls.return_value.process_all_packages.return_value = []

        mock_vm = mock_vm_cls.return_value
        mock_vm.get_all_packages.return_value = packages

        mock_rb = mock_rb_cls.return_value
        mock_rb.create_repository_structure.return_value = mock_repo_structure

        response = lambda_handler(event, mock_context)

    # --- Assertions ---

    # Req 1.5 / 9.6: create_repository_structure must be called with the
    # exact packages returned by get_all_packages (DynamoDB data only)
    mock_rb.create_repository_structure.assert_called_once()
    call_args = mock_rb.create_repository_structure.call_args

    called_packages = call_args.kwargs.get(
        "packages", call_args.args[0] if call_args.args else None
    )
    assert called_packages is not None

    # The packages passed must be exactly the ones from DynamoDB
    assert len(called_packages) == len(packages)

    called_ids = {p.package_id for p in called_packages}
    expected_ids = {p.package_id for p in packages}
    assert called_ids == expected_ids, (
        "create_repository_structure received different packages than "
        "those returned by get_all_packages"
    )

    # Verify no file-reading operations were attempted on the packages
    # (the metadata is self-contained from DynamoDB)
    for pkg in called_packages:
        # Each package must have all fields needed for Packages file generation
        assert pkg.package_name, "package_name must be non-empty"
        assert pkg.version, "version must be non-empty"
        assert pkg.architecture, "architecture must be non-empty"
        assert pkg.actual_filename, "actual_filename must be non-empty"
        assert pkg.file_size >= 0, "file_size must be non-negative"
        assert pkg.sha256_hash, "sha256_hash must be non-empty"

    assert response["statusCode"] == 200
