# Implementation Plan

- [x] 1. Set up project structure and dependencies
  - Create Python project structure with proper module organization
  - Set up pyproject.toml with uv for modern dependency management
  - Add boto3, requests, pytest, hypothesis, and ruff as dependencies
  - Configure ruff for linting and formatting
  - Configure logging and environment variable handling
  - _Requirements: 5.1, 5.5_

- [x] 1.1 Write property test for metadata processing round trip
  - **Property 1: Metadata Processing Round Trip**
  - **Validates: Requirements 1.1, 1.2**

- [x] 2. Implement metadata client for Kiro API
  - Create MetadataClient class with HTTP request handling
  - Implement JSON parsing and validation for the metadata structure
  - Add retry logic with exponential backoff for network failures
  - Run ruff check and format before completion
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2.1 Write property test for version tracking consistency
  - **Property 2: Version Tracking Consistency**
  - **Validates: Requirements 1.5**

- [x] 3. Implement DynamoDB version manager
  - Create VersionManager class with DynamoDB integration
  - Implement version storage with all required fields (version, URLs, timestamp, checksum)
  - Add scan operations with pagination support for retrieving all versions
  - Implement version existence checking logic
  - Run ruff check and format before completion
  - _Requirements: 6.1, 6.2, 6.3, 6.5_

- [x] 3.1 Write property test for DynamoDB storage completeness
  - **Property 7: DynamoDB Storage Completeness**
  - **Validates: Requirements 6.1, 6.2, 6.3**

- [x] 4. Implement package downloader with integrity verification
  - Create PackageDownloader class for downloading .deb, .pem, and .bin files
  - Implement checksum verification using available metadata
  - Add retry logic for failed downloads with exponential backoff
  - Store files in Lambda's ephemeral storage (/tmp)
  - Run ruff check and format before completion
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 4.1 Write property test for download and storage integrity
  - **Property 3: Download and Storage Integrity**
  - **Validates: Requirements 2.1, 2.2, 2.5**

- [x] 5. Implement debian repository builder
  - Create RepositoryBuilder class for generating debian repository structure
  - Implement Packages file generation with metadata for all historical versions
  - Implement Release file generation with checksums and repository information
  - Preserve original package signatures without re-signing
  - Run ruff check and format before completion
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 5.1 Write property test for repository structure completeness
  - **Property 4: Repository Structure Completeness**
  - **Validates: Requirements 3.1, 3.2**

- [x] 5.2 Write property test for repository metadata generation
  - **Property 5: Repository Metadata Generation**
  - **Validates: Requirements 3.3, 3.4, 3.5**

- [x] 6. Implement S3 publisher with proper permissions
  - Create S3Publisher class for uploading repository files
  - Set public read permissions on all uploaded files
  - Configure correct content types for different file extensions
  - Implement upload verification by checking file accessibility
  - Add retry logic for failed uploads
  - Run ruff check and format before completion
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 6.1 Write property test for S3 upload consistency
  - **Property 6: S3 Upload Consistency**
  - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

- [x] 7. Implement comprehensive logging system
  - Create structured logging compatible with CloudWatch
  - Implement operation logging with appropriate detail levels
  - Add success logging with relevant metrics
  - Implement summary logging at system termination
  - Ensure no sensitive data appears in logs
  - Run ruff check and format before completion
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 7.2_

- [x] 7.1 Write property test for logging completeness
  - **Property 8: Logging Completeness**
  - **Validates: Requirements 5.1, 5.3, 5.4, 5.5**

- [x] 7.2 Write property test for security data handling
  - **Property 9: Security Data Handling**
  - **Validates: Requirements 7.2**

- [x] 8. Implement AWS permissions and security validation
  - Add permission validation before AWS resource operations
  - Implement clear error messages for permission failures
  - Ensure IAM role-based authentication throughout
  - Run ruff check and format before completion
  - _Requirements: 7.1, 7.3, 7.4_

- [x] 8.1 Write property test for permission validation
  - **Property 10: Permission Validation**
  - **Validates: Requirements 7.3**

- [x] 9. Create main Lambda handler function
  - Implement main lambda_handler function that orchestrates all components
  - Add error handling and graceful termination logic
  - Integrate all components (metadata client, version manager, downloader, builder, publisher)
  - Implement the complete workflow from metadata check to S3 upload
  - Run ruff check and format before completion
  - _Requirements: All requirements integration_

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Create Terraform infrastructure code
  - Organise terraform files per logical resource, e.g. lambda + its permissions in lambda.tf, etc. Outputs at the bottom of each file, not in a separate outputs.tf
  - Create terraform file with Lambda function configuration (Python 3.12 runtime)
  - Configure DynamoDB table with on-demand billing
  - Set up S3 bucket with public read permissions
  - Create IAM roles with least-privilege permissions
  - Add CloudWatch Events rule for periodic execution
  - Configure SNS topics for success and failure notifications
  - Add CloudWatch alarms and monitoring
  - Support multiple environments through `env` variables and terraform.tfvars files
  - All terraform files should be in terraform/ folder
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 12. Create deployment package and configuration
  - Create deployment script for packaging Lambda function
  - Add environment-specific configuration files
  - _Requirements: 8.5_

- [ ] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Implement installation instructions generator
  - [x] 14.1 Create InstructionsGenerator class
    - Implement generate_index_html method that creates HTML with both installation methods
    - Include repository URL in both quick install (kiro-repo.deb) and manual install sections
    - Generate minimal, clean HTML with basic styling
    - Run ruff check and format before completion
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 14.2 Write property test for installation instructions completeness
    - **Property 11: Installation Instructions Completeness**
    - **Validates: Requirements 9.1, 9.2, 9.3**

  - [x] 14.3 Integrate instructions generator into S3 publisher
    - Generate index.html during repository upload
    - Upload index.html to S3 root with text/html content type
    - Ensure public read permissions on index.html
    - Run ruff check and format before completion
    - _Requirements: 9.4_

- [x] 15. Create kiro-repo package build script
  - Create build-kiro-repo.sh shell script in scripts/ directory
  - Accept parameters for repo URL, version, S3 bucket, and environment
  - Generate debian package structure (DEBIAN/control, DEBIAN/postinst, etc/apt/sources.list.d/kiro.list)
  - Build .deb package using dpkg-deb
  - Upload to S3 with public read permissions
  - Update repository Packages and Release files after upload
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [ ] 16. Create project README.md
  - Write brief README.md in repository root
  - Include description of the Kiro IDE Debian repository
  - Add link to production repository URL only
  - Keep content user-focused and concise
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [ ] 17. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
