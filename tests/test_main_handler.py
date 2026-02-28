"""Integration tests for the main Lambda handler.

Tests cover:
- Normal workflow: new package detected, processed, repository built
- Normal workflow: no new packages, returns early
- Force rebuild workflow: skips package processing, rebuilds from DynamoDB
- Force rebuild: uploads convenience copy for latest kiro-repo
- Error handling: package processing failure returns 500
- Convenience copy: latest kiro-repo version is selected when multiple exist
"""

import os
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.models import PackageMetadata, RepositoryStructure

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context() -> MagicMock:
    """Create a mock Lambda context."""
    ctx = MagicMock()
    ctx.aws_request_id = "test-request-id"
    ctx.function_name = "test-function"
    ctx.function_version = "$LATEST"
    return ctx


def _make_package(
    package_name: str = "kiro",
    version: str = "1.0.0",
    architecture: str = "amd64",
) -> PackageMetadata:
    """Create a minimal PackageMetadata for testing."""
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
        certificate_url=f"https://example.com/{package_name}_{version}.pem",
        signature_url=f"https://example.com/{package_name}_{version}.bin",
    )


ENV_VARS = {
    "S3_BUCKET_NAME": "test-bucket",
    "DYNAMODB_TABLE_NAME": "test-table",
    "AWS_REGION": "us-east-1",
}

# Common patches applied to every test
_BASE_PATCHES = [
    "src.main.validate_iam_role_authentication",
    "src.main.AWSPermissionValidator",
]


# ---------------------------------------------------------------------------
# Test: normal workflow — new package detected
# ---------------------------------------------------------------------------


class TestNormalWorkflowNewPackage:
    """New package detected, processed, repository built and uploaded."""

    def test_normal_workflow_new_package(self):
        """When a new package is found, the full pipeline runs and returns 200."""
        new_pkg = _make_package("kiro", "1.2.0")
        all_pkgs = [new_pkg]
        mock_repo_structure = MagicMock(spec=RepositoryStructure)

        with (
            patch("src.main.validate_iam_role_authentication"),
            patch("src.main.AWSPermissionValidator"),
            patch("src.main.PackageRouter") as mock_router_cls,
            patch("src.main.VersionManager") as mock_vm_cls,
            patch("src.main.RepositoryBuilder") as mock_rb_cls,
            patch("src.main.S3Publisher") as mock_s3_cls,
            patch("src.main.NotificationService") as mock_notif_cls,
            patch.dict(os.environ, ENV_VARS),
        ):
            mock_router_cls.return_value.process_all_packages.return_value = (
                [new_pkg]
            )
            mock_vm_cls.return_value.get_all_packages.return_value = all_pkgs
            mock_rb_cls.return_value.create_repository_structure.return_value = (
                mock_repo_structure
            )

            from src.main import lambda_handler

            response = lambda_handler({}, _make_context())

        assert response["statusCode"] == 200
        assert "1" in response["body"]  # 1 new package processed

        # Repository was built and uploaded
        mock_rb_cls.return_value.create_repository_structure.assert_called_once()
        mock_s3_cls.return_value.upload_repository.assert_called_once_with(
            mock_repo_structure
        )

        # Notification sent for the new package
        mock_notif_cls.return_value.send_success_notification.assert_called_once()

        # Cleanup called
        mock_router_cls.return_value.cleanup_downloads.assert_called_once()

    def test_normal_workflow_passes_all_packages_to_builder(self):
        """create_repository_structure receives all DynamoDB packages, not just new ones."""
        new_pkg = _make_package("kiro", "1.2.0")
        existing_pkg = _make_package("kiro", "1.1.0")
        all_pkgs = [new_pkg, existing_pkg]

        with (
            patch("src.main.validate_iam_role_authentication"),
            patch("src.main.AWSPermissionValidator"),
            patch("src.main.PackageRouter") as mock_router_cls,
            patch("src.main.VersionManager") as mock_vm_cls,
            patch("src.main.RepositoryBuilder") as mock_rb_cls,
            patch("src.main.S3Publisher"),
            patch("src.main.NotificationService"),
            patch.dict(os.environ, ENV_VARS),
        ):
            mock_router_cls.return_value.process_all_packages.return_value = (
                [new_pkg]
            )
            mock_vm_cls.return_value.get_all_packages.return_value = all_pkgs
            mock_rb_cls.return_value.create_repository_structure.return_value = (
                MagicMock()
            )

            from src.main import lambda_handler

            lambda_handler({}, _make_context())

        call_kwargs = (
            mock_rb_cls.return_value.create_repository_structure.call_args.kwargs
        )
        assert len(call_kwargs["packages"]) == 2


# ---------------------------------------------------------------------------
# Test: normal workflow — no new packages
# ---------------------------------------------------------------------------


class TestNormalWorkflowNoNewPackages:
    """No new packages found — handler returns early without building repo."""

    def test_normal_workflow_no_new_packages(self):
        """When no new packages are found, returns 200 with early-exit message."""
        with (
            patch("src.main.validate_iam_role_authentication"),
            patch("src.main.AWSPermissionValidator"),
            patch("src.main.PackageRouter") as mock_router_cls,
            patch("src.main.VersionManager") as mock_vm_cls,
            patch("src.main.RepositoryBuilder") as mock_rb_cls,
            patch("src.main.S3Publisher") as mock_s3_cls,
            patch("src.main.NotificationService"),
            patch.dict(os.environ, ENV_VARS),
        ):
            mock_router_cls.return_value.process_all_packages.return_value = []

            from src.main import lambda_handler

            response = lambda_handler({}, _make_context())

        assert response["statusCode"] == 200
        assert "No new packages" in response["body"]

        # Repository build and upload must NOT happen
        mock_rb_cls.return_value.create_repository_structure.assert_not_called()
        mock_s3_cls.return_value.upload_repository.assert_not_called()
        mock_vm_cls.return_value.get_all_packages.assert_not_called()


# ---------------------------------------------------------------------------
# Test: force rebuild workflow
# ---------------------------------------------------------------------------


class TestForceRebuildWorkflow:
    """force_rebuild=True skips package processing and rebuilds from DynamoDB."""

    def test_force_rebuild_workflow(self):
        """force_rebuild=True skips process_all_packages and uses DynamoDB."""
        all_pkgs = [_make_package("kiro", "1.0.0")]

        with (
            patch("src.main.validate_iam_role_authentication"),
            patch("src.main.AWSPermissionValidator"),
            patch("src.main.PackageRouter") as mock_router_cls,
            patch("src.main.VersionManager") as mock_vm_cls,
            patch("src.main.RepositoryBuilder") as mock_rb_cls,
            patch("src.main.S3Publisher"),
            patch("src.main.NotificationService"),
            patch.dict(os.environ, ENV_VARS),
        ):
            mock_vm_cls.return_value.get_all_packages.return_value = all_pkgs
            mock_rb_cls.return_value.create_repository_structure.return_value = (
                MagicMock()
            )

            from src.main import lambda_handler

            response = lambda_handler({"force_rebuild": True}, _make_context())

        assert response["statusCode"] == 200
        assert "rebuilt" in response["body"].lower()
        assert "1" in response["body"]

        # process_all_packages must NOT be called (or called with force_rebuild=True)
        router = mock_router_cls.return_value
        if router.process_all_packages.called:
            router.process_all_packages.assert_called_with(force_rebuild=True)

        # DynamoDB must be queried for all packages
        mock_vm_cls.return_value.get_all_packages.assert_called_once()

        # Repository must be built and uploaded
        mock_rb_cls.return_value.create_repository_structure.assert_called_once()

    def test_force_rebuild_does_not_send_notifications(self):
        """force_rebuild=True does not send package notifications (no new packages)."""
        all_pkgs = [_make_package("kiro", "1.0.0")]

        with (
            patch("src.main.validate_iam_role_authentication"),
            patch("src.main.AWSPermissionValidator"),
            patch("src.main.PackageRouter"),
            patch("src.main.VersionManager") as mock_vm_cls,
            patch("src.main.RepositoryBuilder") as mock_rb_cls,
            patch("src.main.S3Publisher"),
            patch("src.main.NotificationService") as mock_notif_cls,
            patch.dict(os.environ, ENV_VARS),
        ):
            mock_vm_cls.return_value.get_all_packages.return_value = all_pkgs
            mock_rb_cls.return_value.create_repository_structure.return_value = (
                MagicMock()
            )

            from src.main import lambda_handler

            lambda_handler({"force_rebuild": True}, _make_context())

        # No success notifications for force rebuild (no new packages)
        mock_notif_cls.return_value.send_success_notification.assert_not_called()


# ---------------------------------------------------------------------------
# Test: force rebuild uploads convenience copy
# ---------------------------------------------------------------------------


class TestForceRebuildConvenienceCopy:
    """force_rebuild uploads convenience copy of latest kiro-repo."""

    def test_force_rebuild_uploads_convenience_copy(self):
        """When kiro-repo packages exist, convenience copy is uploaded."""
        kiro_repo_pkg = _make_package("kiro-repo", "1.0.0", "all")
        all_pkgs = [_make_package("kiro", "1.0.0"), kiro_repo_pkg]

        with (
            patch("src.main.validate_iam_role_authentication"),
            patch("src.main.AWSPermissionValidator"),
            patch("src.main.PackageRouter"),
            patch("src.main.VersionManager") as mock_vm_cls,
            patch("src.main.RepositoryBuilder") as mock_rb_cls,
            patch("src.main.S3Publisher") as mock_s3_cls,
            patch("src.main.NotificationService"),
            patch.dict(os.environ, ENV_VARS),
        ):
            mock_vm_cls.return_value.get_all_packages.return_value = all_pkgs
            mock_rb_cls.return_value.create_repository_structure.return_value = (
                MagicMock()
            )

            from src.main import lambda_handler

            lambda_handler({"force_rebuild": True}, _make_context())

        mock_s3_cls.return_value.upload_convenience_copy.assert_called_once_with(
            kiro_repo_pkg
        )

    def test_no_convenience_copy_when_no_kiro_repo(self):
        """When no kiro-repo packages exist, convenience copy is not uploaded."""
        all_pkgs = [_make_package("kiro", "1.0.0")]

        with (
            patch("src.main.validate_iam_role_authentication"),
            patch("src.main.AWSPermissionValidator"),
            patch("src.main.PackageRouter"),
            patch("src.main.VersionManager") as mock_vm_cls,
            patch("src.main.RepositoryBuilder") as mock_rb_cls,
            patch("src.main.S3Publisher") as mock_s3_cls,
            patch("src.main.NotificationService"),
            patch.dict(os.environ, ENV_VARS),
        ):
            mock_vm_cls.return_value.get_all_packages.return_value = all_pkgs
            mock_rb_cls.return_value.create_repository_structure.return_value = (
                MagicMock()
            )

            from src.main import lambda_handler

            lambda_handler({"force_rebuild": True}, _make_context())

        mock_s3_cls.return_value.upload_convenience_copy.assert_not_called()


# ---------------------------------------------------------------------------
# Test: error handling — package processing failure
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Package processing failure returns 500."""

    def test_error_handling_package_processing_failure(self):
        """When PackageRouter raises, handler returns 500."""
        with (
            patch("src.main.validate_iam_role_authentication"),
            patch("src.main.AWSPermissionValidator"),
            patch("src.main.PackageRouter") as mock_router_cls,
            patch("src.main.VersionManager"),
            patch("src.main.RepositoryBuilder"),
            patch("src.main.S3Publisher"),
            patch("src.main.NotificationService"),
            patch.dict(os.environ, ENV_VARS),
        ):
            mock_router_cls.return_value.process_all_packages.side_effect = (
                RuntimeError("DynamoDB connection failed")
            )

            from src.main import lambda_handler

            response = lambda_handler({}, _make_context())

        assert response["statusCode"] == 500
        assert "Error" in response["body"]

    def test_error_handling_repository_build_failure(self):
        """When RepositoryBuilder raises, handler returns 500."""
        new_pkg = _make_package("kiro", "1.0.0")

        with (
            patch("src.main.validate_iam_role_authentication"),
            patch("src.main.AWSPermissionValidator"),
            patch("src.main.PackageRouter") as mock_router_cls,
            patch("src.main.VersionManager") as mock_vm_cls,
            patch("src.main.RepositoryBuilder") as mock_rb_cls,
            patch("src.main.S3Publisher"),
            patch("src.main.NotificationService"),
            patch.dict(os.environ, ENV_VARS),
        ):
            mock_router_cls.return_value.process_all_packages.return_value = (
                [new_pkg]
            )
            mock_vm_cls.return_value.get_all_packages.return_value = [new_pkg]
            mock_rb_cls.return_value.create_repository_structure.side_effect = (
                ValueError("Invalid package metadata")
            )

            from src.main import lambda_handler

            response = lambda_handler({}, _make_context())

        assert response["statusCode"] == 500

    def test_error_handling_sends_failure_notification(self):
        """On error, a failure notification is attempted."""
        with (
            patch("src.main.validate_iam_role_authentication"),
            patch("src.main.AWSPermissionValidator"),
            patch("src.main.PackageRouter") as mock_router_cls,
            patch("src.main.VersionManager"),
            patch("src.main.RepositoryBuilder"),
            patch("src.main.S3Publisher"),
            patch("src.main.NotificationService") as mock_notif_cls,
            patch.dict(os.environ, ENV_VARS),
        ):
            mock_router_cls.return_value.process_all_packages.side_effect = (
                RuntimeError("boom")
            )

            from src.main import lambda_handler

            lambda_handler({}, _make_context())

        mock_notif_cls.return_value.send_failure_notification.assert_called_once()


# ---------------------------------------------------------------------------
# Test: convenience copy uses latest kiro-repo version
# ---------------------------------------------------------------------------


class TestConvenienceCopyLatestVersion:
    """When multiple kiro-repo versions exist, the latest is used."""

    def test_convenience_copy_uses_latest_kiro_repo(self):
        """Latest kiro-repo by semantic version is passed to upload_convenience_copy."""
        pkg_v1 = _make_package("kiro-repo", "1.0.0", "all")
        pkg_v2 = _make_package("kiro-repo", "1.2.0", "all")
        pkg_v3 = _make_package("kiro-repo", "1.10.0", "all")  # semantic > 1.2.0
        kiro_pkg = _make_package("kiro", "2.0.0")
        all_pkgs = [pkg_v1, kiro_pkg, pkg_v3, pkg_v2]  # intentionally unordered

        with (
            patch("src.main.validate_iam_role_authentication"),
            patch("src.main.AWSPermissionValidator"),
            patch("src.main.PackageRouter"),
            patch("src.main.VersionManager") as mock_vm_cls,
            patch("src.main.RepositoryBuilder") as mock_rb_cls,
            patch("src.main.S3Publisher") as mock_s3_cls,
            patch("src.main.NotificationService"),
            patch.dict(os.environ, ENV_VARS),
        ):
            mock_vm_cls.return_value.get_all_packages.return_value = all_pkgs
            mock_rb_cls.return_value.create_repository_structure.return_value = (
                MagicMock()
            )

            from src.main import lambda_handler

            lambda_handler({"force_rebuild": True}, _make_context())

        mock_s3_cls.return_value.upload_convenience_copy.assert_called_once()
        actual_arg = (
            mock_s3_cls.return_value.upload_convenience_copy.call_args.args[0]
        )
        assert actual_arg.version == "1.10.0", (
            f"Expected latest version 1.10.0, got {actual_arg.version}"
        )

    def test_convenience_copy_version_ordering_respects_semver(self):
        """1.9.0 < 1.10.0 (semantic versioning, not lexicographic)."""
        pkg_v9 = _make_package("kiro-repo", "1.9.0", "all")
        pkg_v10 = _make_package("kiro-repo", "1.10.0", "all")
        all_pkgs = [pkg_v10, pkg_v9]  # v10 first to catch naive max()

        with (
            patch("src.main.validate_iam_role_authentication"),
            patch("src.main.AWSPermissionValidator"),
            patch("src.main.PackageRouter"),
            patch("src.main.VersionManager") as mock_vm_cls,
            patch("src.main.RepositoryBuilder") as mock_rb_cls,
            patch("src.main.S3Publisher") as mock_s3_cls,
            patch("src.main.NotificationService"),
            patch.dict(os.environ, ENV_VARS),
        ):
            mock_vm_cls.return_value.get_all_packages.return_value = all_pkgs
            mock_rb_cls.return_value.create_repository_structure.return_value = (
                MagicMock()
            )

            from src.main import lambda_handler

            lambda_handler({"force_rebuild": True}, _make_context())

        actual_arg = (
            mock_s3_cls.return_value.upload_convenience_copy.call_args.args[0]
        )
        assert actual_arg.version == "1.10.0"
