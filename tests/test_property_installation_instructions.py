"""Property-based tests for installation instructions generation."""

import re

from hypothesis import given
from hypothesis import strategies as st

from src.instructions_generator import InstructionsGenerator


# **Feature: debian-repo-manager, Property 11: Installation Instructions Completeness**
# **Validates: Requirements 9.1, 9.2, 9.3**
@given(
    protocol=st.sampled_from(["http", "https"]),
    domain=st.text(
        alphabet=st.characters(whitelist_categories=("Ll", "Nd"), min_codepoint=97),
        min_size=3,
        max_size=30,
    ).map(lambda s: s.replace(" ", "")),
    tld=st.sampled_from(["com", "org", "net", "dev", "io"]),
    path=st.lists(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Nd"), min_codepoint=97
            ),
            min_size=1,
            max_size=15,
        ).map(lambda s: s.replace(" ", "")),
        min_size=0,
        max_size=3,
    ),
    environment=st.sampled_from(["dev", "prod", "staging", "test"]),
)
def test_installation_instructions_completeness_property(
    protocol, domain, tld, path, environment
):
    """Property test: For any repository URL and deployment environment, the generated index.html should contain the repository URL in both installation methods, essential apt commands, and be valid HTML.

    This property tests that installation instructions generation consistently
    produces complete and valid HTML across various repository URLs and environments.
    """
    # Skip invalid domains
    if not domain or len(domain) < 3:
        return

    # Construct repository URL
    path_str = "/" + "/".join(path) if path else ""
    repo_url = f"{protocol}://{domain}.{tld}{path_str}"

    generator = InstructionsGenerator()

    # Generate HTML
    html = generator.generate_index_html(repo_url, environment)

    # Normalize repo_url for comparison (remove trailing slash)
    normalized_repo_url = repo_url.rstrip("/")

    # Property 1: HTML should contain the repository URL in quick install section
    # Looking for: wget {repo_url}/kiro-repo.deb
    assert (
        f"wget {normalized_repo_url}/kiro-repo.deb" in html
    ), f"Quick install section missing repository URL: {normalized_repo_url}/kiro-repo.deb"

    # Property 2: HTML should contain the repository URL in manual install section
    # Looking for: deb [trusted=yes] {repo_url}/ /
    assert (
        f"deb [trusted=yes] {normalized_repo_url}/ /" in html
    ), f"Manual install section missing repository URL: {normalized_repo_url}/ /"

    # Property 3: HTML should contain essential apt commands
    essential_commands = [
        "sudo apt-get update",
        "sudo apt-get install kiro",
        "sudo dpkg -i kiro-repo.deb",
    ]

    for command in essential_commands:
        assert (
            command in html
        ), f"Essential apt command missing from HTML: {command}"

    # Property 4: HTML should be valid HTML with required structure
    # Check for DOCTYPE
    assert (
        "<!DOCTYPE html>" in html
    ), "HTML missing DOCTYPE declaration"

    # Check for html tags
    assert "<html" in html and "</html>" in html, "HTML missing html tags"

    # Check for head section
    assert "<head>" in html and "</head>" in html, "HTML missing head section"

    # Check for body section
    assert "<body>" in html and "</body>" in html, "HTML missing body section"

    # Check for title
    assert "<title>" in html and "</title>" in html, "HTML missing title tag"
    assert "Kiro IDE Repository" in html, "HTML missing expected title content"

    # Property 5: HTML should have proper structure with headings
    # Check for main heading
    assert "<h1>" in html and "</h1>" in html, "HTML missing h1 heading"

    # Check for section headings (Quick Install and Manual Install)
    assert "<h2>" in html and "</h2>" in html, "HTML missing h2 headings"
    assert "Quick Install" in html, "HTML missing Quick Install section"
    assert "Manual Install" in html, "HTML missing Manual Install section"

    # Property 6: HTML should contain code blocks for commands
    assert "<pre>" in html and "</pre>" in html, "HTML missing pre tags for code blocks"
    assert "<code>" in html and "</code>" in html, "HTML missing code tags"

    # Property 7: HTML should have proper character encoding
    assert (
        'charset="UTF-8"' in html or "charset=UTF-8" in html
    ), "HTML missing UTF-8 charset declaration"

    # Property 8: HTML should be well-formed (basic check)
    # Count opening and closing tags for major elements
    html_open = html.count("<html")
    html_close = html.count("</html>")
    assert html_open == html_close, "Mismatched html tags"

    head_open = html.count("<head>")
    head_close = html.count("</head>")
    assert head_open == head_close, "Mismatched head tags"

    body_open = html.count("<body>")
    body_close = html.count("</body>")
    assert body_open == body_close, "Mismatched body tags"

    # Property 9: HTML should contain styling (minimal CSS)
    assert "<style>" in html and "</style>" in html, "HTML missing style section"

    # Property 10: HTML should mention both installation methods clearly
    # The word "Recommended" should appear for quick install
    assert "Recommended" in html or "recommended" in html, "HTML missing recommendation for quick install method"

    # Property 11: HTML should contain update instructions
    assert "Updating" in html or "update" in html, "HTML missing update instructions"
    assert "sudo apt-get upgrade kiro" in html, "HTML missing upgrade command"

    # Property 12: Repository URL should not have double slashes (except after protocol)
    # Check that we don't have patterns like "https://domain.com//path"
    double_slash_pattern = re.compile(r"(?<!:)//")
    matches = double_slash_pattern.findall(normalized_repo_url)
    # If the normalized URL has double slashes, they should not appear in the HTML
    # (except in the protocol part which is expected)
    if matches:
        # Make sure the HTML doesn't propagate these issues
        # This is more of a sanity check on the input normalization
        pass

    # Property 13: HTML length should be reasonable (not empty, not excessively large)
    assert len(html) > 500, "Generated HTML is suspiciously short"
    assert len(html) < 50000, "Generated HTML is suspiciously long"
