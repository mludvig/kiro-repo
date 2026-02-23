# Requirements Document

## Introduction

This feature creates a unified multi-package Debian repository system where all packages (kiro, kiro-repo, kiro-cli) are managed consistently through DynamoDB as the single source of truth. The key innovation is that kiro-repo.deb becomes a proper Debian package in the repository that APT can automatically update, while also being available as a convenience copy at the repository root for initial setup. The system supports multiple package types with different build workflows, uses configuration files to define build parameters, and can rebuild the entire repository from DynamoDB alone without reading from S3.

## Glossary

- **Repository_Manager**: The AWS Lambda function that manages the Debian repository
- **DynamoDB_Store**: The DynamoDB table that serves as the single source of truth for all package versions and metadata
- **Package_Entry**: A record in DynamoDB_Store representing a specific version of a package (kiro, kiro-repo, or kiro-cli)
- **Config_Package**: The kiro-repo.deb package that configures APT sources for the Kiro repository
- **Pool_Directory**: The pool/ directory in the repository where actual .deb files are stored
- **Packages_File**: The Packages metadata file that lists all available packages and their metadata
- **Release_File**: The Release metadata file containing repository information and checksums
- **Convenience_Copy**: A copy of the latest kiro-repo.deb placed at the repository root for easy initial download
- **Build_Script**: The external script that builds kiro-repo.deb and triggers repository updates
- **Force_Rebuild**: A Lambda invocation that rebuilds the entire repository from DynamoDB without fetching new packages
- **Package_Type**: The category of package (kiro, kiro-repo, kiro-cli) with different build and source characteristics
- **Build_Config**: Configuration file defining build parameters for each package type
- **Terraform_State**: The Terraform state file containing infrastructure resource names and identifiers
- **S3_Publisher**: The component that uploads repository files to S3
- **Metadata_Client**: The component that fetches package information from external sources
- **Migration_Script**: A one-time script that transforms existing DynamoDB records from old schema to new schema

## Requirements

### Requirement 1: DynamoDB as Single Source of Truth

**User Story:** As a system architect, I want DynamoDB to be the single source of truth for all packages, so that the repository can be rebuilt without reading from S3.

#### Acceptance Criteria

1. THE DynamoDB_Store SHALL store Package_Entry records for all package types (kiro, kiro-repo, kiro-cli)
2. WHEN storing a Package_Entry, THE DynamoDB_Store SHALL include package name, version, architecture, download URL, file size, and SHA256 checksum
3. WHEN storing a Package_Entry, THE DynamoDB_Store SHALL include package type identifier and processing timestamp
4. WHEN the Repository_Manager performs a Force_Rebuild, THE system SHALL retrieve all Package_Entry records from DynamoDB_Store
5. WHEN building the repository, THE system SHALL use only DynamoDB_Store data without reading package files from S3
6. THE DynamoDB_Store SHALL support querying all versions of a specific package type
7. THE DynamoDB_Store SHALL support querying the latest version of each package type

### Requirement 2: kiro-repo as Proper Repository Package

**User Story:** As a user, I want kiro-repo.deb to be a proper package in the repository, so that APT can automatically detect and install updates.

#### Acceptance Criteria

1. WHEN the Repository_Manager builds the repository, THE system SHALL include kiro-repo.deb in the Pool_Directory
2. WHEN generating the Packages_File, THE system SHALL include kiro-repo package metadata with all standard fields
3. WHEN a user runs apt update, THE APT system SHALL detect kiro-repo as an available package
4. WHEN a newer version of kiro-repo exists, THE APT system SHALL offer it as an upgrade
5. THE kiro-repo package SHALL be stored in pool/main/k/kiro-repo/ following Debian repository conventions
6. THE kiro-repo package SHALL have proper Debian control file metadata (Package, Version, Architecture, Description, Maintainer)

### Requirement 3: Convenience Copy at Repository Root

**User Story:** As a new user, I want to easily download kiro-repo.deb from the repository root, so that I can quickly set up the repository without knowing Debian repository structure.

#### Acceptance Criteria

1. WHEN the Repository_Manager publishes the repository, THE system SHALL create a Convenience_Copy of the latest kiro-repo.deb at the repository root
2. THE Convenience_Copy SHALL be accessible at https://{bucket-url}/kiro-repo.deb
3. WHEN a new version of kiro-repo is published, THE Convenience_Copy SHALL be updated to the latest version
4. THE Convenience_Copy SHALL be a copy of the file, not a redirect or symlink
5. THE Convenience_Copy SHALL have the same content and checksum as the version in Pool_Directory

### Requirement 4: Multi-Package Type Support

**User Story:** As a system maintainer, I want to support multiple package types with different characteristics, so that the repository can host kiro, kiro-repo, and kiro-cli packages.

#### Acceptance Criteria

1. THE Repository_Manager SHALL support three package types: kiro, kiro-repo, and kiro-cli
2. WHEN processing packages, THE system SHALL identify the package type from the Package_Entry metadata
3. WHEN building the repository, THE system SHALL include all package types in the Packages_File
4. WHEN organizing files, THE system SHALL place each package type in its appropriate Pool_Directory subdirectory
5. THE system SHALL support different source workflows for each package type (external download for kiro, build script upload for kiro-repo, future support for kiro-cli)

### Requirement 5: Build Script Integration for kiro-repo

**User Story:** As a developer, I want a build script that creates kiro-repo.deb and triggers repository updates, so that repository configuration changes are deployed automatically.

#### Acceptance Criteria

1. THE Build_Script SHALL create a valid Debian package for kiro-repo with proper metadata
2. WHEN the Build_Script completes, THE script SHALL upload kiro-repo.deb to S3 at a designated staging location
3. WHEN the Build_Script uploads the package, THE script SHALL record the Package_Entry in DynamoDB_Store
4. WHEN the Package_Entry is recorded, THE Build_Script SHALL invoke the Repository_Manager with Force_Rebuild flag
5. THE Build_Script SHALL read infrastructure resource names (bucket, table, function) from Terraform_State
6. THE Build_Script SHALL increment the package version number automatically or accept it as a parameter
7. WHEN the Build_Script fails at any step, THE script SHALL log the error and exit with non-zero status

### Requirement 6: Configuration-Driven Package Definitions

**User Story:** As a system maintainer, I want configuration files to define package build parameters, so that package characteristics are documented and version-controlled.

#### Acceptance Criteria

1. THE system SHALL provide a Build_Config file for each package type
2. WHEN defining a package, THE Build_Config SHALL specify package name, description, maintainer, homepage, and section
3. WHEN defining a package, THE Build_Config SHALL specify source type (external_download, build_script, or future types)
4. WHEN defining kiro packages, THE Build_Config SHALL specify the metadata endpoint URL
5. WHEN defining kiro-repo packages, THE Build_Config SHALL specify the build script path and template locations
6. THE Build_Config SHALL be in a standard format (JSON or YAML)
7. THE Repository_Manager SHALL read Build_Config files at runtime to determine package handling

### Requirement 7: Force Rebuild Capability

**User Story:** As a system operator, I want to force a complete repository rebuild from DynamoDB, so that I can recover from S3 corruption or update repository metadata without new package versions.

#### Acceptance Criteria

1. WHEN invoked with Force_Rebuild flag, THE Repository_Manager SHALL skip checking for new package versions
2. WHEN performing Force_Rebuild, THE Repository_Manager SHALL retrieve all Package_Entry records from DynamoDB_Store
3. WHEN performing Force_Rebuild, THE Repository_Manager SHALL regenerate all repository metadata files (Packages_File, Release_File)
4. WHEN performing Force_Rebuild, THE Repository_Manager SHALL upload all metadata files to S3
5. WHEN performing Force_Rebuild, THE Repository_Manager SHALL update the Convenience_Copy of kiro-repo.deb
6. THE Force_Rebuild operation SHALL complete successfully even if package files are missing from S3
7. THE Force_Rebuild operation SHALL log which packages are included in the rebuilt repository

### Requirement 8: Terraform State Integration

**User Story:** As a developer, I want the build script to read resource names from Terraform state, so that infrastructure changes are automatically reflected without manual configuration updates.

#### Acceptance Criteria

1. THE Build_Script SHALL read the Terraform_State file to obtain S3 bucket name
2. THE Build_Script SHALL read the Terraform_State file to obtain DynamoDB table name
3. THE Build_Script SHALL read the Terraform_State file to obtain Lambda function name
4. WHEN Terraform_State is not found, THE Build_Script SHALL fail with a clear error message
5. WHEN Terraform_State is found but missing required outputs, THE Build_Script SHALL fail with a clear error message
6. THE Build_Script SHALL support specifying the environment (dev, staging, prod) to read the correct state file

### Requirement 9: Package Metadata Completeness

**User Story:** As a system maintainer, I want complete package metadata in DynamoDB, so that the repository can be rebuilt with all necessary information.

#### Acceptance Criteria

1. WHEN storing a Package_Entry for kiro, THE system SHALL include all fields from the external metadata endpoint
2. WHEN storing a Package_Entry for kiro-repo, THE system SHALL include version, size, checksum, and S3 location
3. WHEN storing a Package_Entry, THE system SHALL include Debian control file fields (Package, Version, Architecture, Description, Maintainer, Section, Priority)
4. WHEN storing a Package_Entry, THE system SHALL include file metadata (Filename, Size, SHA256)
5. WHEN storing a Package_Entry, THE system SHALL include processing metadata (timestamp, package type, source)
6. THE Package_Entry SHALL contain sufficient information to generate a complete Packages_File entry without reading the .deb file

### Requirement 10: Repository Metadata Generation

**User Story:** As a system maintainer, I want accurate repository metadata files, so that APT can properly index and verify packages.

#### Acceptance Criteria

1. WHEN generating the Packages_File, THE Repository_Manager SHALL include entries for all Package_Entry records in DynamoDB_Store
2. WHEN generating a Packages_File entry, THE system SHALL include all required Debian fields (Package, Version, Architecture, Maintainer, Filename, Size, SHA256, Description)
3. WHEN generating the Release_File, THE system SHALL include checksums (MD5, SHA1, SHA256) for the Packages_File
4. WHEN generating the Release_File, THE system SHALL include repository metadata (Origin, Label, Suite, Codename, Architectures, Components, Date)
5. THE Packages_File SHALL be generated in the correct format for APT parsing
6. THE Release_File SHALL be generated in the correct format for APT parsing

### Requirement 11: S3 Upload Organization

**User Story:** As a system maintainer, I want proper S3 file organization, so that the repository follows Debian conventions and files are easy to locate.

#### Acceptance Criteria

1. WHEN uploading package files, THE S3_Publisher SHALL place them in pool/main/{first-letter}/{package-name}/ directories
2. WHEN uploading the Packages_File, THE S3_Publisher SHALL place it in dists/stable/main/binary-amd64/
3. WHEN uploading the Release_File, THE S3_Publisher SHALL place it in dists/stable/
4. WHEN uploading the Convenience_Copy, THE S3_Publisher SHALL place it at the repository root
5. WHEN uploading index.html, THE S3_Publisher SHALL place it at the repository root
6. THE S3_Publisher SHALL set appropriate Content-Type headers for each file type
7. THE S3_Publisher SHALL set public read permissions on all uploaded files

### Requirement 12: Automatic kiro-repo Updates

**User Story:** As a user, I want kiro-repo updates to be automatically detected by APT, so that repository configuration changes are applied without manual intervention.

#### Acceptance Criteria

1. WHEN a new version of kiro-repo is published, THE system SHALL include it in the Packages_File with the new version number
2. WHEN a user runs apt update, THE APT system SHALL detect the new kiro-repo version
3. WHEN a user runs apt upgrade, THE APT system SHALL offer to upgrade kiro-repo
4. WHEN kiro-repo is upgraded, THE package postinst script SHALL update the APT sources configuration
5. THE kiro-repo package SHALL follow semantic versioning to indicate the significance of changes

### Requirement 13: Build Script Workflow

**User Story:** As a developer, I want a clear build script workflow, so that I can reliably publish new kiro-repo versions.

#### Acceptance Criteria

1. WHEN invoked, THE Build_Script SHALL accept version number and environment as parameters
2. WHEN building the package, THE Build_Script SHALL create the Debian package directory structure
3. WHEN building the package, THE Build_Script SHALL generate control file with the specified version
4. WHEN building the package, THE Build_Script SHALL generate postinst and prerm scripts
5. WHEN building the package, THE Build_Script SHALL generate the sources.list configuration file with the correct repository URL
6. WHEN building the package, THE Build_Script SHALL use dpkg-deb to create the .deb file
7. WHEN uploading, THE Build_Script SHALL compute SHA256 checksum of the .deb file
8. WHEN recording in DynamoDB, THE Build_Script SHALL include all required Package_Entry fields
9. WHEN triggering rebuild, THE Build_Script SHALL invoke the Lambda function with Force_Rebuild flag
10. THE Build_Script SHALL log each step with clear success or failure messages

### Requirement 14: Error Handling and Logging

**User Story:** As a system operator, I want comprehensive error handling and logging, so that I can diagnose and resolve issues quickly.

#### Acceptance Criteria

1. WHEN any DynamoDB operation fails, THE system SHALL log the error with operation details and retry up to three times
2. WHEN any S3 operation fails, THE system SHALL log the error with file details and retry up to three times
3. WHEN the Build_Script fails, THE script SHALL log which step failed and why
4. WHEN Force_Rebuild is invoked, THE system SHALL log the number of packages being included
5. WHEN the Convenience_Copy is updated, THE system SHALL log the old and new versions
6. WHEN package metadata is incomplete, THE system SHALL log which fields are missing and skip that package
7. THE system SHALL use structured logging with operation context for all major operations

### Requirement 15: One-Time Schema Migration

**User Story:** As a system maintainer, I want a one-time migration script that transforms existing DynamoDB records to the new schema, so that I can safely migrate without maintaining backward compatibility code.

#### Acceptance Criteria

1. THE Migration_Script SHALL read all existing Package_Entry records from DynamoDB_Store using the old schema (version as partition key)
2. WHEN backing up data, THE Migration_Script SHALL export all existing records to a local JSONL file with timestamp
3. WHEN transforming records, THE Migration_Script SHALL convert old schema to new schema with package_id as partition key
4. WHEN transforming kiro package records, THE Migration_Script SHALL add missing fields (package_name="kiro", architecture="amd64", section="utils", priority="optional")
5. WHEN transforming records, THE Migration_Script SHALL add standard Debian metadata fields (maintainer, homepage, description) from Build_Config
6. WHEN uploading transformed records, THE Migration_Script SHALL write new schema records to DynamoDB_Store
7. WHEN all new records are successfully uploaded, THE Migration_Script SHALL delete old schema records from DynamoDB_Store
8. THE Migration_Script SHALL support a dry-run mode that shows transformations without modifying DynamoDB
9. WHEN running in dry-run mode, THE Migration_Script SHALL display old and new record formats for verification
10. THE Migration_Script SHALL log all operations with clear success or failure messages
11. WHEN any operation fails, THE Migration_Script SHALL stop and preserve the backup file for manual recovery
12. THE Migration_Script SHALL verify that all transformed records have required fields before uploading

### Requirement 16: Instructions Page Updates

**User Story:** As a user, I want updated installation instructions, so that I understand the two-step process of installing kiro-repo first, then kiro.

#### Acceptance Criteria

1. WHEN generating the instructions page, THE system SHALL explain that kiro-repo.deb configures the repository
2. WHEN generating the instructions page, THE system SHALL provide the command to download and install kiro-repo.deb from the repository root
3. WHEN generating the instructions page, THE system SHALL explain that after installing kiro-repo, users can install kiro with apt install kiro
4. WHEN generating the instructions page, THE system SHALL explain that kiro-repo will be automatically updated by APT
5. WHEN generating the instructions page, THE system SHALL include manual configuration instructions as an alternative
6. THE instructions page SHALL be uploaded to the repository root as index.html

### Requirement 17: Package Type Extensibility

**User Story:** As a system architect, I want the system to be extensible for future package types, so that adding kiro-cli or other packages requires minimal code changes.

#### Acceptance Criteria

1. THE system SHALL use a plugin or strategy pattern for handling different package types
2. WHEN adding a new package type, THE developer SHALL only need to add a new Build_Config file and implement the source handler
3. THE DynamoDB_Store schema SHALL support arbitrary package types without schema changes
4. THE Repository_Manager SHALL dynamically discover package types from Build_Config files
5. THE Packages_File generation SHALL work for any package type with complete metadata

### Requirement 18: Version Deduplication

**User Story:** As a system operator, I want the system to avoid processing duplicate package versions, so that DynamoDB and S3 storage are used efficiently.

#### Acceptance Criteria

1. WHEN checking for new packages, THE Repository_Manager SHALL query DynamoDB_Store for existing versions
2. WHEN a package version already exists in DynamoDB_Store, THE system SHALL skip downloading and processing
3. WHEN Force_Rebuild is invoked, THE system SHALL skip version checking and use all existing Package_Entry records
4. THE system SHALL log when a package version is skipped due to already being processed
5. THE version comparison SHALL use semantic versioning rules to determine if a version is newer

### Requirement 19: Security and Permissions

**User Story:** As a security engineer, I want proper AWS permissions and secure handling of package data, so that the system follows security best practices.

#### Acceptance Criteria

1. THE Repository_Manager SHALL use IAM roles for all AWS service access
2. THE Build_Script SHALL use IAM credentials or roles for AWS operations
3. WHEN uploading files to S3, THE system SHALL verify write permissions before attempting upload
4. WHEN writing to DynamoDB, THE system SHALL verify write permissions before attempting write
5. THE system SHALL not log sensitive data such as AWS credentials or access keys
6. THE S3 bucket SHALL have public read permissions only on repository files, not on staging or internal files
7. THE Lambda function SHALL have least-privilege IAM permissions for required operations only

### Requirement 20: Testing and Validation

**User Story:** As a developer, I want comprehensive testing, so that I can verify the system works correctly before deploying to production.

#### Acceptance Criteria

1. THE system SHALL include unit tests for all major components (DynamoDB operations, S3 uploads, metadata generation)
2. THE system SHALL include property-based tests for repository metadata generation
3. THE system SHALL include integration tests that verify the complete workflow from package upload to repository publication
4. THE Build_Script SHALL include a dry-run mode that validates the package without uploading
5. THE system SHALL include tests that verify APT can successfully parse the generated repository metadata
6. THE system SHALL include tests that verify the Convenience_Copy matches the Pool_Directory version
7. THE system SHALL include tests that verify Force_Rebuild produces identical output to normal builds (given the same DynamoDB state)
