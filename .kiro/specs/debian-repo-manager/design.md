# Design Document

## Overview

The Debian Repository Manager is a Python-based AWS Lambda function that automatically maintains a debian package repository for Kiro IDE releases. The system monitors the official Kiro metadata endpoint, downloads new package versions, creates a proper debian repository structure with all historical versions, and hosts it on S3 for public access. The solution uses DynamoDB to track processed versions and Terraform for infrastructure deployment.

Based on the metadata structure provided, the system handles three types of files per release:
- The actual debian package (.deb file)
- A certificate file (.pem)
- A signature file (.bin)

## Architecture

The system follows a serverless architecture with the following components:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   CloudWatch    │───▶│  Lambda Function │───▶│   DynamoDB      │
│   Events        │    │  (Python 3.11)  │    │   Version Store │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   S3 Bucket      │
                       │   Debian Repo    │
                       └──────────────────┘
                                ▲
                       ┌──────────────────┐
                       │   External       │
                       │   Metadata API   │
                       └──────────────────┘
```

The Lambda function is triggered periodically (e.g., every hour) via CloudWatch Events to check for new releases. Each execution is stateless and ephemeral - all persistent state is managed through DynamoDB, and repository files are stored in S3.

## Components and Interfaces

### 1. Metadata Client
**Purpose**: Fetches and parses release information from the Kiro metadata endpoint.

**Interface**:
```python
class MetadataClient:
    def fetch_current_metadata(self) -> Dict[str, Any]
    def parse_release_info(self, metadata: Dict) -> List[ReleaseInfo]
```

### 2. Version Manager
**Purpose**: Manages version tracking and comparison using DynamoDB.

**Interface**:
```python
class VersionManager:
    def get_processed_versions(self) -> List[str]
    def is_version_processed(self, version: str) -> bool
    def mark_version_processed(self, release_info: ReleaseInfo) -> None
    def get_all_releases(self) -> List[ReleaseInfo]
```

### 3. Package Downloader
**Purpose**: Downloads debian packages and associated files with retry logic.

**Interface**:
```python
class PackageDownloader:
    def download_release_files(self, release_info: ReleaseInfo) -> LocalReleaseFiles
    def verify_package_integrity(self, files: LocalReleaseFiles) -> bool
```

### 4. Repository Builder
**Purpose**: Creates debian repository structure with proper metadata files.

**Interface**:
```python
class RepositoryBuilder:
    def create_repository_structure(self, releases: List[ReleaseInfo]) -> RepositoryStructure
    def generate_packages_file(self, releases: List[ReleaseInfo]) -> str
    def generate_release_file(self, packages_content: str) -> str
```

### 5. S3 Publisher
**Purpose**: Uploads repository files to S3 with proper permissions and content types.

**Interface**:
```python
class S3Publisher:
    def upload_repository(self, repo_structure: RepositoryStructure) -> None
    def set_public_permissions(self, s3_keys: List[str]) -> None
    def verify_upload_success(self, s3_keys: List[str]) -> bool
```

### 6. Installation Instructions Generator
**Purpose**: Generates HTML installation instructions for the S3-hosted repository.

**Interface**:
```python
class InstructionsGenerator:
    def generate_index_html(self, repo_url: str, environment: str) -> str
```

## Data Models

### ReleaseInfo
```python
@dataclass
class ReleaseInfo:
    version: str
    pub_date: str
    deb_url: str
    certificate_url: str
    signature_url: str
    notes: str
    processed_timestamp: Optional[datetime] = None
```

### LocalReleaseFiles
```python
@dataclass
class LocalReleaseFiles:
    deb_file_path: str
    certificate_path: str
    signature_path: str
    version: str
```

### RepositoryStructure
```python
@dataclass
class RepositoryStructure:
    packages_file_content: str
    release_file_content: str
    deb_files: List[LocalReleaseFiles]
    base_path: str
```

### DynamoDB Schema
**Table Name**: `kiro-package-versions`
**Partition Key**: `version` (String)

**Attributes**:
- `version`: Package version (e.g., "0.7.45")
- `deb_url`: URL to the debian package
- `certificate_url`: URL to the certificate file
- `signature_url`: URL to the signature file
- `pub_date`: Publication date
- `processed_timestamp`: When this version was processed
- `notes`: Release notes

## Correctness Properties
*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

After reviewing the acceptance criteria, several properties can be consolidated to eliminate redundancy:

**Property Reflection:**
- Properties 1.1 and 1.2 can be combined into a single metadata processing property
- Properties 2.1 and 2.5 can be combined into a single download and storage property  
- Properties 3.3 and 3.4 can be combined into a single repository file generation property
- Properties 4.1, 4.2, and 4.3 can be combined into a single S3 upload property
- Properties 6.1 and 6.3 can be combined into a single DynamoDB storage property

**Property 1: Metadata Processing Round Trip**
*For any* valid metadata JSON response from the endpoint, parsing and extracting version information should successfully identify all release entries and their associated URLs
**Validates: Requirements 1.1, 1.2**

**Property 2: Version Tracking Consistency**
*For any* extracted version information, querying DynamoDB should correctly identify whether the version has been processed previously
**Validates: Requirements 1.5**

**Property 3: Download and Storage Integrity**
*For any* valid package URLs, downloading and storing files should result in accessible local files that match the expected checksums when available
**Validates: Requirements 2.1, 2.2, 2.5**

**Property 4: Repository Structure Completeness**
*For any* set of historical package versions, the generated repository structure should include all versions in the Packages file and maintain proper debian repository format
**Validates: Requirements 3.1, 3.2**

**Property 5: Repository Metadata Generation**
*For any* collection of debian packages, the generated Packages and Release files should contain accurate metadata, checksums, and preserve original signatures
**Validates: Requirements 3.3, 3.4, 3.5**

**Property 6: S3 Upload Consistency**
*For any* repository structure, uploading to S3 should result in all files being publicly accessible with correct content types and permissions
**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

**Property 7: DynamoDB Storage Completeness**
*For any* new package version, storing in DynamoDB should include all required fields (version, URLs, timestamp, checksum) and be retrievable via scan operations
**Validates: Requirements 6.1, 6.2, 6.3**

**Property 8: Logging Completeness**
*For any* system operation, appropriate log messages should be generated with structured format compatible with CloudWatch
**Validates: Requirements 5.1, 5.3, 5.4, 5.5**

**Property 9: Security Data Handling**
*For any* log output, sensitive data such as credentials or access keys should not be present in log messages
**Validates: Requirements 7.2**

**Property 10: Permission Validation**
*For any* AWS resource access attempt, the system should validate permissions before performing operations
**Validates: Requirements 7.3**

**Property 11: Installation Instructions Completeness**
*For any* repository URL and deployment environment, the generated index.html should contain the repository URL in both installation methods (quick install with kiro-repo.deb and manual configuration), essential apt commands, and be valid HTML
**Validates: Requirements 9.1, 9.2, 9.3**

## Error Handling

The system implements comprehensive error handling with the following strategies:

### Network Errors
- HTTP request failures trigger exponential backoff retry (up to 3 attempts)
- Connection timeouts result in graceful termination with detailed logging
- Invalid SSL certificates are logged and cause operation failure

### Data Processing Errors
- JSON parsing errors are caught and logged with the malformed content
- Missing required fields in metadata trigger validation errors
- Checksum mismatches cause package rejection and retry

### AWS Service Errors
- DynamoDB throttling triggers exponential backoff retry
- S3 upload failures retry with different strategies based on error type
- IAM permission errors provide clear diagnostic messages

### File System Errors
- Disk space issues are detected before large downloads
- Temporary file cleanup occurs even on failure paths
- File permission errors are logged with suggested remediation

## Testing Strategy

The testing approach combines unit testing and property-based testing to ensure comprehensive coverage:

### Unit Testing Framework
- **Framework**: pytest for Python unit testing
- **Coverage**: Specific examples, integration points, and error conditions
- **Focus**: Concrete scenarios like parsing known metadata formats, handling specific error codes

### Property-Based Testing Framework
- **Framework**: Hypothesis for Python property-based testing
- **Configuration**: Minimum 100 iterations per property test
- **Coverage**: Universal properties that should hold across all inputs
- **Focus**: General correctness across the input space

### Test Organization
- Unit tests verify specific examples and edge cases
- Property tests verify universal behaviors across generated inputs
- Integration tests validate AWS service interactions
- Each property-based test includes a comment referencing the design document property

### Test Data Generation
- Smart generators that constrain to valid input spaces
- Metadata generators that produce valid JSON structures
- Version generators that create realistic version numbers
- URL generators that produce valid download endpoints

## Deployment Architecture

### Lambda Configuration
- **Runtime**: Python 3.12 (latest supported version)
- **Memory**: 1024 MB (sufficient for debian package processing)
- **Timeout**: 15 minutes (maximum Lambda timeout)
- **Environment Variables**: S3 bucket name, DynamoDB table name, log level
- **Ephemeral Storage**: 512 MB for temporary file processing (files are not persisted between runs)

### Trigger Configuration
- **Schedule**: CloudWatch Events rule (hourly execution)
- **Dead Letter Queue**: SQS queue for failed executions
- **Retry Policy**: 2 retries with exponential backoff

### Resource Requirements
- **DynamoDB**: On-demand billing mode for variable workload
- **S3**: Standard storage class with public read access
- **IAM**: Least-privilege roles for Lambda execution

### Monitoring and Alerting
- CloudWatch metrics for execution duration, errors, and success rate
- CloudWatch alarms for failed executions and high error rates
- SNS topic for critical failures and error notifications
- SNS topic for successful package updates and repository refreshes

## Security Considerations

### Authentication and Authorization
- Lambda execution role with minimal required permissions
- S3 bucket policy allowing public read access only
- DynamoDB access limited to specific table operations

### Data Protection
- No sensitive data stored in logs or temporary files
- HTTPS-only communication with external endpoints
- Temporary files cleaned up after processing

### Network Security
- Lambda runs in AWS managed VPC
- Outbound HTTPS access to Kiro metadata endpoint
- No inbound network access required

## Performance Considerations

### Scalability
- Single Lambda execution handles one check cycle
- DynamoDB auto-scaling handles variable read/write loads
- S3 handles unlimited concurrent downloads

### Optimization
- Parallel downloads of multiple release files
- Efficient DynamoDB queries using scan with pagination
- Streaming uploads to S3 for large files

### Resource Management
- Temporary files stored in Lambda's ephemeral storage (/tmp) and automatically cleaned up after execution
- All persistent data stored in DynamoDB (version tracking, metadata)
- All repository files stored in S3 (no local file system persistence)
- Connection pooling for HTTP requests
- Memory-efficient streaming for large package downloads
- No reading from S3 for operational data - all state managed through DynamoDB

## Installation Instructions Implementation

### Two-Step Installation Approach

The system provides two installation methods to balance ease-of-use with flexibility:

1. **Quick Install (Recommended)**: Install the `kiro-repo` configuration package
2. **Manual Install**: Directly configure sources.list for advanced users

### HTML Generation
The system generates a minimal index.html page with both installation methods:

```html
<!DOCTYPE html>
<html>
<head>
    <title>Kiro IDE Repository</title>
    <style>/* Minimal styling for readability */</style>
</head>
<body>
    <h1>Kiro IDE Debian Repository</h1>
    
    <h2>Quick Install (Recommended)</h2>
    <pre>
# Download and install repository configuration
wget https://{repo-url}/kiro-repo.deb
sudo dpkg -i kiro-repo.deb
sudo apt-get update
sudo apt-get install kiro
    </pre>
    
    <h2>Manual Install</h2>
    <pre>
# Add repository manually
echo "deb [trusted=yes] https://{repo-url}/ /" | sudo tee /etc/apt/sources.list.d/kiro.list
sudo apt-get update
sudo apt-get install kiro
    </pre>
</body>
</html>
```

### Repository Configuration Package (kiro-repo)

The `kiro-repo` package is a manually-created debian package that:
- Adds the appropriate `/etc/apt/sources.list.d/kiro.list` entry
- Configures GPG keys or certificates if needed
- Can be updated to change repository URLs without breaking existing installations
- Is versioned (e.g., `kiro-repo_1.0_all.deb`, `kiro-repo_1.1_all.deb`)

**Package Structure**:
```
kiro-repo/
├── DEBIAN/
│   ├── control          # Package metadata
│   └── postinst         # Post-installation script
└── etc/
    └── apt/
        └── sources.list.d/
            └── kiro.list    # Repository configuration
```

**Build and Upload Script**:
A shell script (`build-kiro-repo.sh`) handles:
1. Creating the debian package directory structure
2. Generating control file with version and metadata
3. Creating postinst script for repository configuration
4. Building the .deb package using `dpkg-deb`
5. Uploading to S3 with public read permissions
6. Updating the Packages and Release files in the repository

The script accepts parameters for:
- Repository URL (dev/prod)
- Package version
- S3 bucket name
- Environment (dev/prod)

**Benefits**:
- Users can easily switch repository URLs by installing an updated kiro-repo package
- Centralized configuration management
- Standard Debian package management workflow
- No manual file editing required

**Note**: The Lambda function does NOT build this package. The build script is run manually when the repository URL needs to be updated or initially set up.

### Environment Configuration
- Repository URL is injected from environment variables (REPO_URL or derived from S3 bucket name)
- Environment name (dev/prod) is passed to the generator
- HTML is uploaded to S3 root as `index.html` with `text/html` content type
- The kiro-repo.deb package is manually uploaded to S3 root

### README Content
The project README.md (in git repository root, not S3) is a static file that includes:
- Brief description: "Automated Debian repository for Kiro IDE releases"
- Link to production repository: `https://{prod-bucket-url}/`
- No dev repository link (internal use only)
- No implementation details or developer setup instructions

This file is manually created and committed to the git repository, not generated by the Lambda.