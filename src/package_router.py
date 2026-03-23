"""Package routing and orchestration for multi-package repository."""

import glob
import logging
import os

from src.config_manager import ConfigManager, PackageConfig
from src.models import PackageMetadata
from src.package_handlers import (
    KiroPackageHandler,
    KiroRepoPackageHandler,
    PackageHandler,
)
from src.version_manager import VersionManager

logger = logging.getLogger(__name__)


class PackageRouter:
    """Routes package processing to appropriate handlers based on config."""

    def __init__(
        self,
        config_dir: str = "config/packages",
        validate_permissions: bool = True,
    ) -> None:
        """Initialize router with configs and handlers.

        Args:
            config_dir: Path to package configuration directory.
            validate_permissions: Whether to validate AWS permissions.
        """
        self.config_manager = ConfigManager(config_dir=config_dir)
        self.version_manager = VersionManager(
            validate_permissions=validate_permissions,
        )
        self.handlers: dict[str, PackageHandler] = {}

        for config in self.config_manager.load_all_configs():
            handler = self._create_handler(config)
            self.handlers[config.package_name] = handler
            logger.info("Registered handler for package: %s", config.package_name)

    def _create_handler(self, config: PackageConfig) -> PackageHandler:
        """Create the appropriate handler for a package config.

        Args:
            config: Package configuration.

        Returns:
            A PackageHandler instance for the source type.

        Raises:
            ValueError: If the source type is unknown or not implemented.
        """
        source_type = config.source.type
        logger.debug(
            "Routing package '%s' to handler for source type '%s'",
            config.package_name,
            source_type,
        )
        if source_type == "external_download":
            logger.info(
                "Package '%s' routed to KiroPackageHandler (external_download)",
                config.package_name,
            )
            return KiroPackageHandler(config)
        if source_type == "build_script":
            logger.info(
                "Package '%s' routed to KiroRepoPackageHandler (build_script)",
                config.package_name,
            )
            return KiroRepoPackageHandler(config)
        if source_type == "github_release":
            raise ValueError(
                f"Source type '{source_type}' is not yet implemented"
            )
        raise ValueError(f"Unknown source type: '{source_type}'")

    def process_all_packages(
        self,
        force_rebuild: bool = False,
    ) -> list[PackageMetadata]:
        """Process all registered packages for new versions.

        Args:
            force_rebuild: If True, skip version checking and return
                empty list. Caller retrieves packages from DynamoDB.

        Returns:
            List of newly processed package metadata.
        """
        if force_rebuild:
            logger.info(
                "Force rebuild requested - skipping version checks for %d package(s): %s",
                len(self.handlers),
                ", ".join(self.handlers.keys()),
            )
            return []

        results: list[PackageMetadata] = []

        for package_name, handler in self.handlers.items():
            try:
                logger.info("Checking for new version: %s", package_name)
                version = handler.check_new_version()

                if version is None:
                    logger.info("No new version found for %s", package_name)
                    continue

                if self.version_manager.is_package_version_processed(
                    package_name, version
                ):
                    logger.info(
                        "Version %s already processed for %s",
                        version,
                        package_name,
                    )
                    continue

                logger.info(
                    "Acquiring package %s version %s",
                    package_name,
                    version,
                )
                metadata = handler.acquire_package(version)
                self.version_manager.store_package_metadata(metadata)
                results.append(metadata)
                logger.info(
                    "Successfully processed %s version %s",
                    package_name,
                    version,
                )

            except Exception:
                logger.exception(
                    "Error processing package %s", package_name
                )

        return results

    def cleanup_downloads(self) -> None:
        """Clean up temporary download files from /tmp."""
        patterns = ["/tmp/*.deb", "/tmp/*.cert", "/tmp/*.sig"]
        for pattern in patterns:
            for filepath in glob.glob(pattern):
                try:
                    os.remove(filepath)
                    logger.info("Removed temporary file: %s", filepath)
                except OSError:
                    logger.exception(
                        "Failed to remove file: %s", filepath
                    )
