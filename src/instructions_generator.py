"""Generator for installation instructions HTML page."""

import logging


class InstructionsGenerator:
    """Generates HTML installation instructions for the Debian repository."""

    def __init__(self, logger: logging.Logger | None = None):
        """Initialize the instructions generator.

        Args:
            logger: Optional logger instance for operation logging
        """
        self.logger = logger or logging.getLogger(__name__)

    def generate_index_html(self, repo_url: str, environment: str = "prod") -> str:
        """Generate HTML installation instructions page.

        Creates a minimal, clean HTML page with two installation methods:
        1. Quick install using kiro-repo.deb configuration package
        2. Manual install by directly configuring sources.list

        Args:
            repo_url: The base URL of the repository (e.g., https://bucket.s3.region.amazonaws.com)
            environment: Deployment environment (dev/prod) for display purposes

        Returns:
            Complete HTML document as a string

        Validates: Requirements 9.1, 9.2, 9.3
        """
        self.logger.info(
            "Generating installation instructions HTML",
            extra={
                "repo_url": repo_url,
                "environment": environment,
                "component": "instructions_generator",
            },
        )

        # Ensure repo_url doesn't have trailing slash
        repo_url = repo_url.rstrip("/")

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kiro IDE Repository</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
        }}
        pre {{
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 15px;
            overflow-x: auto;
            font-size: 14px;
        }}
        code {{
            font-family: 'Courier New', Courier, monospace;
            color: #e83e8c;
        }}
        .note {{
            background-color: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 12px;
            margin: 20px 0;
        }}
        .recommended {{
            color: #28a745;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Kiro IDE Debian Repository</h1>

        <p>Welcome to the Kiro IDE Debian repository. This repository provides easy installation and updates for Kiro IDE on Debian and Ubuntu systems.</p>

        <h2>Quick Install <span class="recommended">(Recommended)</span></h2>
        <p>Download and install the repository configuration package, then install Kiro IDE:</p>
        <pre><code># Download and install repository configuration
wget {repo_url}/kiro-repo.deb
sudo dpkg -i kiro-repo.deb

# Update package list and install Kiro IDE
sudo apt-get update
sudo apt-get install kiro</code></pre>

        <h2>Manual Install</h2>
        <p>For advanced users who prefer to configure the repository manually:</p>
        <pre><code># Add repository to sources list
echo "deb [trusted=yes] {repo_url}/ /" | sudo tee /etc/apt/sources.list.d/kiro.list

# Update package list and install Kiro IDE
sudo apt-get update
sudo apt-get install kiro</code></pre>

        <div class="note">
            <strong>Note:</strong> The <code>[trusted=yes]</code> option is used because the repository uses self-signed certificates. This is safe for the official Kiro repository.
        </div>

        <h2>Updating Kiro IDE</h2>
        <p>Once the repository is configured, you can update Kiro IDE using standard apt commands:</p>
        <pre><code>sudo apt-get update
sudo apt-get upgrade kiro</code></pre>
    </div>
</body>
</html>"""

        self.logger.info(
            "Successfully generated installation instructions HTML",
            extra={
                "html_length": len(html_content),
                "component": "instructions_generator",
            },
        )

        return html_content
