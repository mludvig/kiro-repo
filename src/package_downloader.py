"""Package downloader with integrity verification and retry logic."""

import hashlib
import logging
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.models import LocalReleaseFiles, ReleaseInfo

logger = logging.getLogger(__name__)


class PackageDownloader:
    """Downloads debian packages and associated files with retry logic and integrity verification."""

    def __init__(self, download_dir: str = "/tmp", timeout: int = 300):
        """Initialize the package downloader.

        Args:
            download_dir: Directory to store downloaded files (default: /tmp for Lambda)
            timeout: Request timeout in seconds
        """
        self.download_dir = Path(download_dir)
        self.timeout = timeout
        self.session = self._create_session()

        # Ensure download directory exists
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry configuration.

        Returns:
            Configured requests session with exponential backoff retry
        """
        session = requests.Session()

        # Configure retry strategy with exponential backoff
        retry_strategy = Retry(
            total=3,  # Maximum 3 retries as per requirements
            backoff_factor=1,  # Exponential backoff: 1, 2, 4 seconds
            status_forcelist=[429, 500, 502, 503, 504],  # HTTP status codes to retry
            allowed_methods=["GET"],  # Only retry GET requests
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def download_release_files(self, release_info: ReleaseInfo) -> LocalReleaseFiles:
        """Download all files for a release (deb, certificate, signature).

        Args:
            release_info: Release information containing URLs

        Returns:
            LocalReleaseFiles with paths to downloaded files

        Raises:
            requests.RequestException: If download fails after all retries
            ValueError: If file integrity verification fails
        """
        logger.info(f"Starting download for version {release_info.version}")

        # Create version-specific directory
        version_dir = self.download_dir / f"kiro-{release_info.version}"
        version_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Extract original filenames from URLs
            deb_filename = self._extract_filename_from_url(release_info.deb_url)
            cert_filename = self._extract_filename_from_url(release_info.certificate_url)
            sig_filename = self._extract_filename_from_url(release_info.signature_url)
            
            # Download each file type with original names
            deb_path = self._download_file(
                release_info.deb_url, version_dir, deb_filename
            )
            cert_path = self._download_file(
                release_info.certificate_url, version_dir, cert_filename
            )
            sig_path = self._download_file(
                release_info.signature_url, version_dir, sig_filename
            )

            local_files = LocalReleaseFiles(
                deb_file_path=str(deb_path),
                certificate_path=str(cert_path),
                signature_path=str(sig_path),
                version=release_info.version,
            )

            logger.info(
                f"Successfully downloaded all files for version {release_info.version}"
            )
            return local_files

        except Exception as e:
            logger.error(
                f"Failed to download files for version {release_info.version}: {e}"
            )
            # Clean up partial downloads
            self._cleanup_directory(version_dir)
            raise

    def _download_file(self, url: str, target_dir: Path, filename: str) -> Path:
        """Download a single file with retry logic.

        Args:
            url: URL to download from
            target_dir: Directory to save the file
            filename: Name for the downloaded file

        Returns:
            Path to the downloaded file

        Raises:
            requests.RequestException: If download fails after all retries
        """
        target_path = target_dir / filename

        logger.info(f"Downloading {filename} from {url}")

        try:
            response = self.session.get(url, timeout=self.timeout, stream=True)
            response.raise_for_status()

            # Write file in chunks to handle large files efficiently
            with open(target_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:  # Filter out keep-alive chunks
                        f.write(chunk)

            file_size = target_path.stat().st_size
            logger.info(f"Successfully downloaded {filename} ({file_size} bytes)")

            return target_path

        except requests.RequestException as e:
            logger.error(f"Failed to download {filename} from {url}: {e}")
            # Clean up partial file
            if target_path.exists():
                target_path.unlink()
            raise

    def verify_package_integrity(
        self, files: LocalReleaseFiles, expected_checksum: str | None = None
    ) -> bool:
        """Verify the integrity of downloaded files.

        Args:
            files: Local file paths to verify
            expected_checksum: Expected SHA256 checksum (if available)

        Returns:
            True if all files pass integrity checks

        Raises:
            ValueError: If integrity verification fails
        """
        logger.info(f"Verifying integrity of files for version {files.version}")

        # Check that all files exist and are readable
        file_paths = [files.deb_file_path, files.certificate_path, files.signature_path]

        for file_path in file_paths:
            path = Path(file_path)
            if not path.exists():
                raise ValueError(f"Downloaded file does not exist: {file_path}")

            if path.stat().st_size == 0:
                raise ValueError(f"Downloaded file is empty: {file_path}")

        # Verify checksum if provided
        if expected_checksum:
            actual_checksum = self._calculate_sha256(files.deb_file_path)
            if actual_checksum != expected_checksum:
                raise ValueError(
                    f"Checksum mismatch for {files.deb_file_path}. "
                    f"Expected: {expected_checksum}, Got: {actual_checksum}"
                )
            logger.info("Checksum verification passed")

        logger.info(f"Integrity verification passed for version {files.version}")
        return True

    def _calculate_sha256(self, file_path: str) -> str:
        """Calculate SHA256 checksum of a file.

        Args:
            file_path: Path to the file

        Returns:
            SHA256 checksum as hex string
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    def _extract_filename_from_url(self, url: str) -> str:
        """Extract filename from URL.

        Args:
            url: URL to extract filename from

        Returns:
            Filename extracted from URL
        """
        # Extract filename from URL path
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        filename = Path(parsed_url.path).name
        
        # Fallback to generic names if extraction fails
        if not filename:
            if url.endswith('.deb') or 'deb' in url:
                filename = "package.deb"
            elif url.endswith('.pem') or 'certificate' in url:
                filename = "certificate.pem"
            elif url.endswith('.bin') or 'signature' in url:
                filename = "signature.bin"
            else:
                filename = "unknown_file"
        
        return filename

    def _cleanup_directory(self, directory: Path) -> None:
        """Clean up a directory and its contents.

        Args:
            directory: Directory to clean up
        """
        try:
            if directory.exists():
                for file_path in directory.iterdir():
                    if file_path.is_file():
                        file_path.unlink()
                directory.rmdir()
                logger.info(f"Cleaned up directory: {directory}")
        except Exception as e:
            logger.warning(f"Failed to clean up directory {directory}: {e}")

    def cleanup_all_downloads(self) -> None:
        """Clean up all downloaded files in the download directory."""
        try:
            for item in self.download_dir.iterdir():
                if item.is_dir() and item.name.startswith("kiro-"):
                    self._cleanup_directory(item)
            logger.info("Cleaned up all download directories")
        except Exception as e:
            logger.warning(f"Failed to clean up download directories: {e}")
