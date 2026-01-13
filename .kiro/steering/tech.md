# Technology Stack

## Core Technologies

- **Python 3.12+**: Primary programming language
- **AWS Lambda**: Serverless compute platform
- **Terraform**: Infrastructure as Code
- **AWS Services**: S3, DynamoDB, CloudWatch, SNS

## Dependencies

### Production Dependencies
- `boto3>=1.34.0`: AWS SDK for Python
- `requests>=2.31.0`: HTTP library with retry logic
- `python-dateutil>=2.8.2`: Date/time utilities

### Development Dependencies
- `pytest>=7.4.0`: Testing framework
- `hypothesis>=6.88.0`: Property-based testing
- `ruff>=0.1.0`: Linting and formatting

## Build System

The project uses modern Python packaging with `pyproject.toml` and supports both `uv` (preferred) and `pip` for dependency management.

### Package Manager
- **Preferred**: `uv` for faster dependency resolution and installation
- **Fallback**: `pip` with virtual environments

### Code Quality
- **Linter/Formatter**: Ruff with line length of 88 characters
- **Target Version**: Python 3.12
- **Import Sorting**: Enabled via Ruff

## Common Commands

### Development Setup

Always use `uv` for dependency management and virtual environments.

```bash
uv sync
uv run pytest
uv run ruff ...
```

### Testing
```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src
```

### Code Quality
```bash
# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/

# Fix auto-fixable issues
uv run ruff check --fix src/ tests/
```

### Deployment
```bash
# Deploy to development
./deploy.sh dev plan
./deploy.sh dev apply

# Deploy to production
./deploy.sh prod plan
./deploy.sh prod apply
```
