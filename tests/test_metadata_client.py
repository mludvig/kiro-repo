"""Tests for the metadata client."""

import json
from unittest.mock import Mock, patch

import pytest
import requests

from src.metadata_client import MetadataClient


class TestMetadataClient:
    """Unit tests for MetadataClient."""

    def test_fetch_current_metadata_success(self):
        """Test successful metadata fetching."""
        client = MetadataClient()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "version": "0.7.45",
            "pub_date": "2024-01-15",
            "url": "https://example.com/package.deb",
            "certificate": "https://example.com/cert.pem",
            "signature": "https://example.com/sig.bin",
            "notes": "Test release",
        }

        with patch.object(client.session, "get", return_value=mock_response):
            metadata = client.fetch_current_metadata()

        assert metadata["version"] == "0.7.45"
        assert metadata["url"] == "https://example.com/package.deb"

    def test_parse_release_info_success(self):
        """Test successful release info parsing."""
        client = MetadataClient()
        metadata = {
            "version": "0.7.45",
            "pub_date": "2024-01-15",
            "url": "https://example.com/package.deb",
            "certificate": "https://example.com/cert.pem",
            "signature": "https://example.com/sig.bin",
            "notes": "Test release",
        }

        releases = client.parse_release_info(metadata)

        assert len(releases) == 1
        release = releases[0]
        assert release.version == "0.7.45"
        assert release.deb_url == "https://example.com/package.deb"
        assert release.certificate_url == "https://example.com/cert.pem"
        assert release.signature_url == "https://example.com/sig.bin"

    def test_parse_release_info_missing_fields(self):
        """Test parsing with missing required fields."""
        client = MetadataClient()
        metadata = {
            "version": "0.7.45",
            # Missing required fields
        }

        with pytest.raises(ValueError, match="Missing required fields"):
            client.parse_release_info(metadata)

    def test_fetch_metadata_network_error(self):
        """Test handling of network errors."""
        client = MetadataClient()

        with patch.object(
            client.session,
            "get",
            side_effect=requests.RequestException("Network error"),
        ):
            with pytest.raises(requests.RequestException):
                client.fetch_current_metadata()

    def test_fetch_metadata_invalid_json(self):
        """Test handling of invalid JSON response."""
        client = MetadataClient()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_response.text = "Invalid JSON content"

        with patch.object(client.session, "get", return_value=mock_response):
            with pytest.raises(json.JSONDecodeError):
                client.fetch_current_metadata()
