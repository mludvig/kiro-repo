# Project Structure

## Directory Organization

```
├── src/                    # Main application source code
├── tests/                  # Test suite (unit and property-based tests)
├── terraform/              # Infrastructure as Code
├── config/                 # Environment-specific configuration files
├── .kiro/steering/         # AI assistant guidance documents
├── build/                  # Build artifacts (generated)
└── deploy.sh              # Deployment automation script
```

## Source Code Structure (`src/`)

### Core Modules
- `main.py`: Lambda entry point and orchestration logic
- `config.py`: Configuration management and structured logging setup
- `models.py`: Data classes and type definitions

### Business Logic Modules
- `metadata_client.py`: Fetches Kiro release metadata from API
- `package_downloader.py`: Downloads and verifies package files
- `version_manager.py`: Tracks processed versions in DynamoDB
- `repository_builder.py`: Creates Debian repository structure
- `s3_publisher.py`: Uploads repository to S3
- `aws_permissions.py`: AWS IAM permission validation

## Test Structure (`tests/`)

### Test Categories
- `test_*.py`: Standard unit tests
- `test_property_*.py`: Property-based tests using Hypothesis

### Test Patterns
- Each source module has corresponding unit tests
- Property-based tests validate system invariants
- Tests use mocking for external dependencies (AWS, HTTP)

## Infrastructure (`terraform/`)

### Terraform Files
- `main.tf`: Provider configuration and basic setup
- `variables.tf`: Input variable definitions
- `lambda.tf`: Lambda function and related resources
- `s3.tf`: S3 bucket for repository hosting
- `dynamodb.tf`: Version tracking table
- `cloudwatch.tf`: Logging and monitoring
- `sns.tf`: Notification setup

### Configuration Files
- `terraform.tfvars.example`: Template for environment variables
- `config/*.tfvars`: Environment-specific configurations

## Coding Conventions

### Python Style
- **Line Length**: 88 characters (Black/Ruff standard)
- **Import Organization**: Standard library, third-party, local imports
- **Type Hints**: Required for all function signatures
- **Docstrings**: Google-style docstrings for all public functions

### Error Handling
- Use structured logging with operation tracking
- Comprehensive exception handling with context
- AWS service errors should be caught and logged appropriately

### Data Classes
- Use `@dataclass` for data structures
- Include type hints for all fields
- Provide `from_*` class methods for data transformation

### AWS Integration
- All AWS operations should include permission validation
- Use boto3 with proper error handling and retries
- Log all AWS operations with structured metadata

## File Naming Conventions

### Python Files
- Snake_case for module names
- Classes use PascalCase
- Functions and variables use snake_case
- Constants use UPPER_SNAKE_CASE

### Test Files
- Unit tests: `test_<module_name>.py`
- Property tests: `test_property_<feature>.py`
- Test classes: `Test<ClassName>`
- Test methods: `test_<behavior>`

### Terraform Files
- Resource-specific files: `<service>.tf` (e.g., `s3.tf`)
- Environment configs: `<env>.tfvars` (e.g., `dev.tfvars`)

## Architecture Patterns

### Dependency Injection
- Components receive dependencies via constructor
- Enable/disable permission validation for testing
- Use factory patterns for AWS client creation

### Operation Logging
- All major operations use `OperationLogger`
- Track timing, success/failure, and relevant metadata
- Structured JSON logging for CloudWatch integration

### Error Recovery
- Graceful degradation where possible
- Comprehensive cleanup in error scenarios
- Detailed error context for debugging