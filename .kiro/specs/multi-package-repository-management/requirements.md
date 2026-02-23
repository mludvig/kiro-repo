# Requirements Document

## Introduction

This document specifies the requirements for extending the Debian Repository Manager to support multiple package types (kiro-ide, kiro-repo, kiro-cli) with DynamoDB as the single source of truth for all package metadata. The system will use configuration files for build parameters and integrate the kiro-repo package into the main repository workflow.

## Glossary

- **Package_Name**: The identifier for a package (kiro, kiro-repo, kiro-cli, etc.)
- **DynamoDB_Package_Store**: The DynamoDB table that stores metadata for all packages
- **Build_Configuration**: JSON/YAML files containing build parameters for each package
- **Kiro_Repo_Package**: A debian package that configures the system to use the Kiro repository
- **Force_Rebuild**: A Lambda operation that regenerates repository files from DynamoDB without downloading new packages
- **Package_Metadata_Entry**: A DynamoDB record containing all information about a specific package version
- **Build_Script**: A shell script that builds a package, uploads it to S3, and records metadata in DynamoDB
- **Terraform_State**: The Terraform state file containing infrastructure resource information

## Requirements

### Requirement 1

**User Story:** As a system maintainer, I want DynamoDB to be the single source of truth for all package metadata, so that the repository can be rebuilt consistently without reading from S3.

#### Acceptance Criteria

1. WHEN storing package metadata, THE system SHALL include package name (kiro, kiro-repo, kiro-cli) as a field
2. WHEN querying packages, THE system SHALL retrieve all packages from DynamoDB
3. WHEN building repository files, THE system SHALL use only DynamoDB data without reading existing Packages files from S3
4. WHEN a force rebuild occurs, THE system SHALL generate complete repository metadata from DynamoDB alone
5. WHEN multiple packages exist, THE system SHALL include all packages in the generated Packages file

### Requirement 2

**User Story:** As a developer, I want build configuration stored in versioned files, so that build parameters are tracked and consistent across environments.

#### Acceptance Criteria

1. THE system SHALL store build configuration in JSON or YAML files within a kiro-repo-deb/ directory
2. WHEN building a package, THE system SHALL read configuration from the appropriate file
3. WHEN configuration includes environment-specific settings, THE system SHALL support dev and prod configurations
4. WHEN configuration changes, THE system SHALL allow version tracking through git
5. THE configuration files SHALL include repository URL, package version, S3 bucket, and environment

### Requirement 3

**User Story:** As a system maintainer, I want the build script to record package metadata in DynamoDB, so that all packages are tracked consistently.

#### Acceptance Criteria

1. WHEN a kiro-repo package is built, THE build script SHALL upload the .deb file to S3
2. WHEN the upload succeeds, THE build script SHALL record package metadata in DynamoDB
3. WHEN recording metadata, THE system SHALL include package name, version, URLs, checksums, and file size
4. WHEN recording metadata, THE system SHALL use the same DynamoDB table as kiro packages
5. WHEN metadata is recorded, THE system SHALL include a timestamp for tracking

### Requirement 4

**User Story:** As a system maintainer, I want the build script to read DynamoDB table names from Terraform state, so that it works correctly across environments without hardcoding.

#### Acceptance Criteria

1. WHEN the build script executes, THE system SHALL read the DynamoDB table name from Terraform state
2. WHEN reading Terraform state, THE system SHALL use the environment parameter (dev/prod) to select the correct state file
3. WHEN the Terraform state is unavailable, THE system SHALL provide a clear error message
4. WHEN the table name is retrieved, THE system SHALL use it for all DynamoDB operations
5. WHEN multiple environments exist, THE system SHALL correctly identify the appropriate table for each

### Requirement 5

**User Story:** As a system maintainer, I want to trigger a force rebuild after uploading kiro-repo packages, so that repository metadata is updated to include the new package.

#### Acceptance Criteria

1. WHEN a kiro-repo package is uploaded and recorded in DynamoDB, THE build script SHALL trigger a force rebuild
2. WHEN triggering a force rebuild, THE system SHALL invoke the Lambda function with the force_rebuild flag
3. WHEN the force rebuild completes, THE system SHALL verify that repository files include the new package
4. WHEN the force rebuild fails, THE system SHALL provide clear error messages
5. WHEN triggering rebuilds, THE system SHALL use the correct Lambda function for the environment

### Requirement 6

**User Story:** As a developer, I want the Lambda function to handle multiple packages, so that all packages are included in repository metadata.

#### Acceptance Criteria

1. WHEN retrieving packages from DynamoDB, THE Lambda SHALL query all packages
2. WHEN generating the Packages file, THE Lambda SHALL include entries for all packages
3. WHEN generating package entries, THE Lambda SHALL use package-specific metadata
4. WHEN building repository structure, THE Lambda SHALL organize packages by name in the pool directory
5. WHEN multiple versions of a package exist, THE Lambda SHALL include all versions

### Requirement 7

**User Story:** As a system maintainer, I want the DynamoDB schema to support multiple packages, so that different packages can coexist with appropriate metadata.

#### Acceptance Criteria

1. WHEN storing package metadata, THE system SHALL include a package_name field (kiro, kiro-repo, kiro-cli)
2. WHEN storing package metadata, THE system SHALL use a composite key or appropriate schema to support multiple packages
3. WHEN querying packages, THE system SHALL efficiently retrieve packages by name or all packages
4. WHEN packages have different metadata requirements, THE system SHALL support optional fields

### Requirement 8

**User Story:** As a system maintainer, I want the kiro-repo package organized in a dedicated directory structure, so that build artifacts and configuration are clearly separated.

#### Acceptance Criteria

1. THE system SHALL create a kiro-repo-deb/ directory in the repository root
2. WHEN organizing files, THE system SHALL place build configuration in kiro-repo-deb/config/
3. WHEN organizing files, THE system SHALL place build scripts in kiro-repo-deb/scripts/ or use the existing scripts/ directory
4. WHEN organizing files, THE system SHALL place documentation in kiro-repo-deb/README.md
5. THE directory structure SHALL be documented and consistent across environments

### Requirement 9

**User Story:** As a system maintainer, I want the build script to validate configuration before building, so that errors are caught early.

#### Acceptance Criteria

1. WHEN the build script starts, THE system SHALL validate that required configuration fields are present
2. WHEN configuration is invalid, THE system SHALL provide clear error messages indicating missing or incorrect fields
3. WHEN validating configuration, THE system SHALL check that URLs are properly formatted
4. WHEN validating configuration, THE system SHALL verify that version numbers follow semantic versioning
5. WHEN validation fails, THE system SHALL exit before attempting to build or upload

### Requirement 10

**User Story:** As a developer, I want comprehensive logging during the build and upload process, so that I can troubleshoot issues effectively.

#### Acceptance Criteria

1. WHEN the build script executes, THE system SHALL log each major operation with timestamps
2. WHEN uploading to S3, THE system SHALL log upload progress and success/failure
3. WHEN recording to DynamoDB, THE system SHALL log the metadata being stored
4. WHEN triggering force rebuild, THE system SHALL log the Lambda invocation and response
5. WHEN errors occur, THE system SHALL log detailed error information with context
