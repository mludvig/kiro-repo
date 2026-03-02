"""Tests for the instructions generator."""

import logging
from unittest.mock import Mock

from src.instructions_generator import InstructionsGenerator


class TestInstructionsGenerator:
    """Unit tests for InstructionsGenerator."""

    def test_generate_index_html_basic(self):
        """Test basic HTML generation with a simple URL."""
        generator = InstructionsGenerator()
        repo_url = "https://example.s3.amazonaws.com"

        html = generator.generate_index_html(repo_url)

        assert html is not None
        assert len(html) > 0
        assert "<!DOCTYPE html>" in html
        assert repo_url in html

    def test_generate_index_html_contains_repo_url(self):
        """Verify the repo URL appears in both quick and manual install sections."""
        generator = InstructionsGenerator()
        repo_url = "https://kiro-repo.s3.us-east-1.amazonaws.com"

        html = generator.generate_index_html(repo_url)

        # URL should appear in quick install section
        assert f"wget {repo_url}/kiro-repo.deb" in html

        # URL should appear in manual install section
        assert f'echo "deb [trusted=yes] {repo_url}/ /"' in html

        # URL should appear in the info box
        assert f"{repo_url}/index.html" in html

    def test_generate_index_html_contains_kiro_repo_explanation(self):
        """Verify 'What is kiro-repo?' section is present."""
        generator = InstructionsGenerator()
        repo_url = "https://example.s3.amazonaws.com"

        html = generator.generate_index_html(repo_url)

        # Check for the section heading
        assert "What is kiro-repo?" in html

        # Check for key explanation content
        assert "kiro-repo" in html
        assert "repository configuration package" in html
        assert "automatically sets up your system" in html

    def test_generate_index_html_contains_two_step_process(self):
        """Verify two-step installation process is explained."""
        generator = InstructionsGenerator()
        repo_url = "https://example.s3.amazonaws.com"

        html = generator.generate_index_html(repo_url)

        # Check for two-step process description
        assert "two-step process" in html

        # Check for step labels
        assert "Step 1:" in html
        assert "Step 2:" in html

        # Check for step descriptions
        assert "Download and install repository configuration" in html
        assert "Update package list and install Kiro IDE" in html

    def test_generate_index_html_contains_automatic_updates(self):
        """Verify automatic updates explanation is present."""
        generator = InstructionsGenerator()
        repo_url = "https://example.s3.amazonaws.com"

        html = generator.generate_index_html(repo_url)

        # Check for automatic updates section
        assert "Automatic Updates:" in html

        # Check for key content about automatic updates
        assert "kiro-repo" in html
        assert "automatically updated by APT" in html
        assert "repository configuration stays current" in html
        assert "don't need to manually reinstall" in html

    def test_generate_index_html_contains_manual_install(self):
        """Verify manual installation section is present."""
        generator = InstructionsGenerator()
        repo_url = "https://example.s3.amazonaws.com"

        html = generator.generate_index_html(repo_url)

        # Check for manual install section
        assert "Manual Install" in html

        # Check for manual install description
        assert "advanced users" in html
        assert "configure the repository manually" in html

        # Check for trusted=yes note
        assert "[trusted=yes]" in html
        assert "self-signed certificates" in html

    def test_generate_index_html_contains_all_commands(self):
        """Verify all essential apt commands are present."""
        generator = InstructionsGenerator()
        repo_url = "https://example.s3.amazonaws.com"

        html = generator.generate_index_html(repo_url)

        # Quick install commands
        assert "wget" in html
        assert "sudo dpkg -i kiro-repo.deb" in html
        assert "sudo apt-get update" in html
        assert "sudo apt-get install kiro" in html

        # Manual install commands
        assert "sudo tee /etc/apt/sources.list.d/kiro.list" in html

        # Update commands
        assert "sudo apt-get upgrade kiro" in html

    def test_generate_index_html_valid_structure(self):
        """Verify HTML has valid structure (DOCTYPE, html, head, body tags)."""
        generator = InstructionsGenerator()
        repo_url = "https://example.s3.amazonaws.com"

        html = generator.generate_index_html(repo_url)

        # Check for essential HTML structure
        assert "<!DOCTYPE html>" in html
        assert '<html lang="en">' in html
        assert "<head>" in html
        assert "</head>" in html
        assert "<body>" in html
        assert "</body>" in html
        assert "</html>" in html

        # Check for meta tags
        assert '<meta charset="UTF-8">' in html
        assert '<meta name="viewport"' in html

        # Check for title
        assert "<title>Kiro IDE Repository</title>" in html

        # Check for CSS
        assert "<style>" in html
        assert "</style>" in html

    def test_generate_index_html_with_different_environments(self):
        """Test with different environment values (dev, prod, staging)."""
        generator = InstructionsGenerator()
        repo_url = "https://example.s3.amazonaws.com"

        # Test with different environments
        for env in ["dev", "prod", "staging"]:
            html = generator.generate_index_html(repo_url, environment=env)

            # HTML should be generated regardless of environment
            assert html is not None
            assert len(html) > 0
            assert "<!DOCTYPE html>" in html

    def test_generate_index_html_normalizes_trailing_slash(self):
        """Verify trailing slashes are removed from repo URL."""
        generator = InstructionsGenerator()
        repo_url_with_slash = "https://example.s3.amazonaws.com/"
        repo_url_without_slash = "https://example.s3.amazonaws.com"

        html_with_slash = generator.generate_index_html(repo_url_with_slash)
        html_without_slash = generator.generate_index_html(repo_url_without_slash)

        # Both should produce identical output
        assert html_with_slash == html_without_slash

        # Verify no double slashes in URLs
        assert "amazonaws.com//" not in html_with_slash
        assert f"{repo_url_without_slash}/kiro-repo.deb" in html_with_slash

    def test_generate_index_html_with_custom_logger(self):
        """Test that custom logger is used when provided."""
        mock_logger = Mock(spec=logging.Logger)
        generator = InstructionsGenerator(logger=mock_logger)
        repo_url = "https://example.s3.amazonaws.com"

        html = generator.generate_index_html(repo_url)

        # Verify logger was called
        assert mock_logger.info.called
        assert html is not None

    def test_generate_index_html_logs_operation(self):
        """Test that HTML generation logs appropriate messages."""
        mock_logger = Mock(spec=logging.Logger)
        generator = InstructionsGenerator(logger=mock_logger)
        repo_url = "https://example.s3.amazonaws.com"
        environment = "prod"

        html = generator.generate_index_html(repo_url, environment=environment)

        # Verify logging calls
        assert mock_logger.info.call_count == 2

        # Check first log call (start of generation)
        first_call = mock_logger.info.call_args_list[0]
        assert "Generating installation instructions HTML" in first_call[0][0]
        assert first_call[1]["extra"]["repo_url"] == repo_url
        assert first_call[1]["extra"]["environment"] == environment

        # Check second log call (completion)
        second_call = mock_logger.info.call_args_list[1]
        assert (
            "Successfully generated installation instructions HTML" in second_call[0][0]
        )
        assert "html_length" in second_call[1]["extra"]
        assert second_call[1]["extra"]["html_length"] == len(html)

    def test_generate_index_html_contains_recommended_badge(self):
        """Verify quick install is marked as recommended."""
        generator = InstructionsGenerator()
        repo_url = "https://example.s3.amazonaws.com"

        html = generator.generate_index_html(repo_url)

        # Check for recommended badge
        assert "Recommended" in html
        assert 'class="recommended"' in html

    def test_generate_index_html_contains_styling(self):
        """Verify HTML contains proper styling for readability."""
        generator = InstructionsGenerator()
        repo_url = "https://example.s3.amazonaws.com"

        html = generator.generate_index_html(repo_url)

        # Check for CSS classes
        assert 'class="container"' in html
        assert 'class="note"' in html
        assert 'class="info"' in html

        # Check for styling elements
        assert "background-color" in html
        assert "border-radius" in html
        assert "font-family" in html

    def test_generate_index_html_contains_update_section(self):
        """Verify update instructions section is present."""
        generator = InstructionsGenerator()
        repo_url = "https://example.s3.amazonaws.com"

        html = generator.generate_index_html(repo_url)

        # Check for update section
        assert "Updating Kiro IDE" in html

        # Check for update instructions
        assert "standard apt commands" in html
        assert "sudo apt-get update" in html
        assert "sudo apt-get upgrade kiro" in html

    def test_generate_index_html_with_complex_url(self):
        """Test with complex S3 URL including region."""
        generator = InstructionsGenerator()
        repo_url = "https://my-kiro-repo.s3.us-west-2.amazonaws.com"

        html = generator.generate_index_html(repo_url)

        # Verify URL is correctly embedded
        assert repo_url in html
        assert f"wget {repo_url}/kiro-repo.deb" in html
        assert f'echo "deb [trusted=yes] {repo_url}/ /"' in html

    def test_generate_index_html_default_logger(self):
        """Test that default logger is created when none provided."""
        generator = InstructionsGenerator()

        # Verify logger exists
        assert generator.logger is not None
        assert isinstance(generator.logger, logging.Logger)

        # Should be able to generate HTML without errors
        html = generator.generate_index_html("https://example.com")
        assert html is not None
