"""Metadata client for fetching Kiro package information."""

import json
import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import ReleaseInfo

logger = logging.getLogger(__name__)


class MetadataClient:
    """Client for fetching and parsing Kiro package metadata."""

    METADATA_URL = "https://prod.download.desktop.kiro.dev/stable/metadata-linux-x64-deb-stable.json"

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        """Initialize the metadata client.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry configuration."""
        session = requests.Session()

        # Configure retry strategy with exponential backoff
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,  # 1, 2, 4 seconds
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def fetch_current_metadata(self) -> dict[str, Any]:
        """Fetch current package metadata from the Kiro endpoint.

        Returns:
            Dictionary containing the parsed JSON metadata

        Raises:
            requests.RequestException: If the request fails after all retries
            json.JSONDecodeError: If the response contains invalid JSON
        """
        logger.info(f"Fetching metadata from {self.METADATA_URL}")

        try:
            response = self.session.get(self.METADATA_URL, timeout=self.timeout)
            response.raise_for_status()

            logger.info(
                f"Successfully fetched metadata (status: {response.status_code})"
            )

            # Parse JSON response
            metadata = response.json()
            logger.debug(f"Parsed metadata: {json.dumps(metadata, indent=2)}")

            return metadata

        except requests.exceptions.RequestException as e:
            logger.error(
                f"Failed to fetch metadata after {self.max_retries} retries: {e}"
            )
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse metadata JSON: {e}")
            logger.error(f"Response content: {response.text[:500]}...")
            raise

    def parse_release_info(self, metadata: dict[str, Any]) -> list[ReleaseInfo]:
        """Parse release information from metadata.

        Args:
            metadata: Raw metadata dictionary from the API

        Returns:
            List of ReleaseInfo objects

        Raises:
            KeyError: If required fields are missing from metadata
            ValueError: If metadata structure is invalid
        """
        logger.info("Parsing release information from metadata")

        try:
            # Check if this is the new nested structure
            if "releases" in metadata and "currentRelease" in metadata:
                return self._parse_nested_metadata(metadata)

            # Fallback to old flat structure
            return self._parse_flat_metadata(metadata)

        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse release information: {e}")
            logger.error(f"Metadata structure: {json.dumps(metadata, indent=2)}")
            raise

    def _parse_nested_metadata(self, metadata: dict[str, Any]) -> list[ReleaseInfo]:
        """Parse the new nested metadata structure."""
        releases = metadata.get("releases", [])
        metadata.get("currentRelease")

        if not releases:
            raise ValueError("No releases found in metadata")

        # Group releases by version to collect all URLs for each version
        version_data = {}

        for release in releases:
            version = release.get("version")
            update_to = release.get("updateTo", {})

            if not version or not update_to:
                continue

            if version not in version_data:
                version_data[version] = {
                    "version": version,
                    "pub_date": update_to.get("pub_date", ""),
                    "notes": update_to.get("notes", ""),
                    "urls": [],
                }

            url = update_to.get("url", "")
            if url:
                version_data[version]["urls"].append(url)

        # Convert to ReleaseInfo objects
        release_infos = []

        for version, data in version_data.items():
            urls = data["urls"]

            # Identify URLs by their file extensions/patterns
            deb_url = ""
            certificate_url = ""
            signature_url = ""

            for url in urls:
                if url.endswith(".deb"):
                    deb_url = url
                elif url.endswith("certificate.pem") or "certificate" in url:
                    certificate_url = url
                elif url.endswith("signature.bin") or "signature" in url:
                    signature_url = url

            if not deb_url:
                logger.warning(f"No .deb file found for version {version}")
                continue

            release_info = ReleaseInfo(
                version=data["version"],
                pub_date=data["pub_date"],
                deb_url=deb_url,
                certificate_url=certificate_url,
                signature_url=signature_url,
                notes=data["notes"],
            )

            release_infos.append(release_info)

            logger.info(f"Parsed release info for version {version}")
            logger.debug(f"Release info: {release_info}")

        if not release_infos:
            raise ValueError("No valid release information could be parsed")

        # Sort by version (newest first) and return
        release_infos.sort(key=lambda x: x.version, reverse=True)
        return release_infos

    def _parse_flat_metadata(self, metadata: dict[str, Any]) -> list[ReleaseInfo]:
        """Parse the old flat metadata structure."""
        # Validate required top-level fields
        required_fields = ["version", "pub_date", "url", "certificate", "signature"]
        missing_fields = [field for field in required_fields if field not in metadata]

        if missing_fields:
            raise ValueError(f"Missing required fields in metadata: {missing_fields}")

        # Create ReleaseInfo from metadata
        release_info = ReleaseInfo.from_metadata(metadata)

        logger.info(
            f"Successfully parsed release info for version {release_info.version}"
        )
        logger.debug(f"Release info: {release_info}")

        return [release_info]

    def get_current_release(self) -> ReleaseInfo:
        """Fetch and parse the current release information.

        Returns:
            ReleaseInfo object for the current release

        Raises:
            requests.RequestException: If fetching metadata fails
            json.JSONDecodeError: If JSON parsing fails
            ValueError: If metadata structure is invalid
        """
        metadata = self.fetch_current_metadata()
        releases = self.parse_release_info(metadata)

        if not releases:
            raise ValueError("No release information found in metadata")

        return releases[0]
