"""Package handler for Kiro IDE packages from external metadata endpoint."""

import logging

from src.config_manager import PackageConfig
from src.metadata_client import MetadataClient
from src.models import PackageMetadata
from src.package_downloader import PackageDownloader
from src.package_handlers.base import PackageHandler

logger = logging.getLogger(__name__)


class KiroPackageHandler(PackageHandler):
    """Handles Kiro IDE package discovery, download, and metadata.

    Fetches release metadata from an external endpoint, downloads
    .deb packages with certificates and signatures, and produces
    PackageMetadata for repository generation.

    Attributes:
        metadata_client: Client for fetching release metadata
        downloader: Downloader for package files
    """

    def __init__(self, config: PackageConfig) -> None:
        """Initialize the Kiro package handler.

        Args:
            config: Package configuration with source endpoint details
        """
        super().__init__(config)

        metadata_url = config.source.metadata_endpoint
        if not metadata_url:
            raise ValueError(
                f"Package '{config.package_name}' is missing required "
                "'source.metadata_endpoint' in its config"
            )
        self.metadata_client = MetadataClient(metadata_url=metadata_url)
        self.downloader = PackageDownloader()

    def check_new_version(self) -> str | None:
        """Check for the latest available Kiro version.

        Returns:
            Version string if available, None on failure
        """
        try:
            release_info = self.metadata_client.get_current_release()
            logger.info(
                "Current Kiro version: %s", release_info.version
            )
            return release_info.version
        except Exception:
            logger.exception("Failed to check for new Kiro version")
            return None

    def acquire_package(self, version: str) -> PackageMetadata:
        """Acquire a Kiro package for the given version.

        Downloads the .deb, certificate, and signature files, verifies
        integrity, populates file metadata, and returns PackageMetadata.

        Args:
            version: Version string to acquire

        Returns:
            PackageMetadata with all fields populated

        Raises:
            ValueError: If integrity verification fails
            requests.RequestException: If downloads fail
        """
        release_info = self.metadata_client.get_current_release()

        local_files = self.downloader.download_release_files(
            release_info
        )
        self.downloader.verify_package_integrity(local_files)
        self.downloader.populate_file_metadata(
            release_info, local_files
        )

        return PackageMetadata(
            package_name=self.config.package_name,
            version=release_info.version,
            architecture=self.config.architecture,
            pub_date=release_info.pub_date,
            deb_url=release_info.deb_url,
            actual_filename=release_info.actual_filename,
            file_size=release_info.file_size,
            md5_hash=release_info.md5_hash,
            sha1_hash=release_info.sha1_hash,
            sha256_hash=release_info.sha256_hash,
            certificate_url=release_info.certificate_url,
            signature_url=release_info.signature_url,
            notes=release_info.notes,
            section=self.config.section,
            priority=self.config.priority,
            maintainer=self.config.maintainer,
            homepage=self.config.homepage,
            description=self.config.description,
            depends=release_info.depends or self.config.depends,
        )

    def get_package_file_path(self, metadata: PackageMetadata) -> str:
        """Get the local file path for a downloaded Kiro package.

        Args:
            metadata: Package metadata identifying the package

        Returns:
            Local filesystem path to the .deb file
        """
        return f"/tmp/kiro-{metadata.version}/{metadata.actual_filename}"
