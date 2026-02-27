# Implementation Plan: Unified Multi-Package Repository

## Overview

This implementation transforms the existing single-package Debian repository manager into a unified multi-package system where DynamoDB serves as the single source of truth. The system will support multiple package types (kiro, kiro-repo, kiro-cli) with different build workflows, use configuration files to define package parameters, and enable force rebuild capabilities from DynamoDB alone.

Key architectural changes:
- DynamoDB schema update with composite key (package_id = package_name#version)
- Configuration-driven package type routing with YAML config files
- Plugin-based package handler architecture for extensibility
- kiro-repo.deb as proper repository package with convenience copy at root
- Build script for kiro-repo package creation and deployment
- One-time migration script for schema transformation

## Tasks

- [ ] 1. Create configuration management infrastructure
  - [x] 1.1 Add PyYAML dependency to pyproject.toml
    - Add `pyyaml>=6.0` to dependencies section
    - Run `uv sync` to update lock file
    - _Requirements: 6.6_
  
  - [x] 1.2 Create package configuration directory structure
    - Create `config/packages/` directory
    - _Requirements: 6.1_
  
  - [x] 1.3 Implement configuration data models
    - Create `src/config_manager.py` with `SourceConfig` and `PackageConfig` dataclasses
    - Implement `from_yaml()` class method for loading from YAML files
    - _Requirements: 6.2, 6.3, 6.4, 6.5_
  
  - [x] 1.4 Implement ConfigManager class
    - Implement `load_all_configs()` method to discover and load all package configs
    - Implement `get_config(package_name)` method for specific package lookup
    - _Requirements: 6.7_
  
  - [ ]* 1.5 Write property test for configuration file completeness
    - **Property 20: Configuration File Completeness**
    - **Validates: Requirements 6.2, 6.3**
  
  - [ ]* 1.6 Write property test for configuration file format
    - **Property 21: Configuration File Format**
    - **Validates: Requirements 6.6**

- [x] 2. Create package configuration files
  - [x] 2.1 Create kiro.yaml configuration
    - Define package metadata (name, description, maintainer, homepage, section, priority, architecture)
    - Configure external_download source with metadata endpoint URL
    - Specify additional files (certificate, signature)
    - _Requirements: 6.2, 6.3, 6.4_
  
  - [x] 2.2 Create kiro-repo.yaml configuration
    - Define package metadata with architecture="all"
    - Configure build_script source with staging prefix
    - Document build script path and template locations
    - _Requirements: 6.2, 6.3, 6.5_
  
  - [x] 2.3 Create kiro-cli.yaml configuration (placeholder for future)
    - Define package metadata with depends="kiro (>= 1.0)"
    - Configure github_release source (commented out/placeholder)
    - _Requirements: 6.2, 6.3, 17.2_

- [x] 3. Update data models and utilities
  - [x] 3.1 Update PackageMetadata model in src/models.py
    - Verify all fields present: package_name, version, architecture, section, priority, maintainer, homepage, description, depends
    - Add package_id property that returns f"{package_name}#{version}"
    - _Requirements: 1.2, 1.3, 9.3, 9.4, 9.5_
  
  - [x] 3.2 Create version parsing utility
    - Create `src/utils.py` with `parse_version()` function
    - Implement semantic version parsing to tuple for comparison
    - Handle edge cases (non-standard versions, missing parts)
    - _Requirements: 12.5, 18.5_
  
  - [x]* 3.3 Write property test for semantic version comparison
    - **Property 19: Semantic Version Comparison**
    - **Validates: Requirements 12.5, 18.5**

- [-] 4. Update DynamoDB version manager
  - [x] 4.1 Update VersionManager to use new schema
    - Change primary key from "version" to "package_id" (format: "package_name#version")
    - Update `is_version_processed()` to `is_package_version_processed(package_name, version)`
    - Update `store_version_metadata()` to `store_package_metadata(metadata: PackageMetadata)`
    - Add `get_all_packages()` method that scans entire table
    - Add `get_packages_by_name(package_name)` method with filter expression
    - Add `get_latest_package(package_name)` method using version parsing
    - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 18.2_
  
  - [x] 4.2 Write property test for multi-package type storage
    - **Property 1: Multi-Package Type Storage**
    - **Validates: Requirements 1.1, 4.1, 4.2, 17.3**
  
  - [x] 4.3 Write property test for package metadata completeness
    - **Property 2: Package Metadata Completeness**
    - **Validates: Requirements 1.2, 1.3, 9.3, 9.4, 9.5**
  
  - [x] 4.4 Write property test for package query by name
    - **Property 5: Package Query by Name**
    - **Validates: Requirements 1.6**
  
  - [x] 4.5 Write property test for latest version identification
    - **Property 6: Latest Version Identification**
    - **Validates: Requirements 1.7**
  
  - [x] 4.6 Write property test for version deduplication
    - **Property 18: Version Deduplication**
    - **Validates: Requirements 18.2**

- [ ] 5. Checkpoint - Verify configuration and data layer
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implement package handler base class and interface
  - [ ] 6.1 Create package handlers directory
    - Create `src/package_handlers/` directory
    - Create `src/package_handlers/__init__.py`
    - _Requirements: 17.1_
  
  - [ ] 6.2 Implement PackageHandler abstract base class
    - Create `src/package_handlers/base.py` with abstract methods
    - Define `check_new_version()` method signature
    - Define `acquire_package(version)` method signature
    - Define `get_package_file_path(metadata)` method signature
    - _Requirements: 17.1, 17.2_

- [ ] 7. Implement kiro package handler
  - [ ] 7.1 Create KiroPackageHandler class
    - Create `src/package_handlers/kiro_handler.py`
    - Implement `check_new_version()` using existing MetadataClient
    - Implement `acquire_package()` using existing PackageDownloader
    - Implement `get_package_file_path()` returning /tmp path
    - Convert ReleaseInfo to PackageMetadata with config fields
    - _Requirements: 4.5, 9.1_
  
  - [ ]* 7.2 Write unit tests for KiroPackageHandler
    - Test version checking with mocked metadata endpoint
    - Test package acquisition and metadata conversion
    - Test error handling for download failures

- [ ] 8. Implement kiro-repo package handler
  - [ ] 8.1 Create KiroRepoPackageHandler class
    - Create `src/package_handlers/kiro_repo_handler.py`
    - Implement `check_new_version()` returning None (triggered by build script)
    - Implement `acquire_package()` raising NotImplementedError (build script stores metadata)
    - Implement `get_package_file_path()` downloading from S3 staging area
    - _Requirements: 4.5, 5.2, 5.3_
  
  - [ ]* 8.2 Write unit tests for KiroRepoPackageHandler
    - Test S3 staging area download with mocked S3 client
    - Test error handling for missing files

- [ ] 9. Implement package router
  - [ ] 9.1 Create PackageRouter class
    - Create `src/package_router.py` with PackageRouter class
    - Implement `__init__()` loading all configs and creating handlers
    - Implement `_create_handler()` factory method based on source type
    - Support "external_download", "build_script", and "github_release" types
    - _Requirements: 4.1, 4.2, 17.2_
  
  - [ ] 9.2 Implement process_all_packages method
    - Iterate through all handlers checking for new versions
    - Skip version checking if force_rebuild=True
    - Check DynamoDB for existing versions before processing
    - Call handler.acquire_package() for new versions
    - Store metadata in DynamoDB via VersionManager
    - Handle errors per-package without stopping others
    - Return list of newly processed packages
    - _Requirements: 4.3, 18.1, 18.2_
  
  - [ ] 9.3 Add cleanup_downloads method
    - Clean up /tmp files after processing
    - _Requirements: 14.1_
  
  - [ ]* 9.4 Write unit tests for PackageRouter
    - Test handler creation for different source types
    - Test process_all_packages with multiple package types
    - Test force_rebuild skips version checking
    - Test error isolation between packages

- [ ] 10. Checkpoint - Verify package handling layer
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Update repository builder for multi-package support
  - [ ] 11.1 Update create_repository_structure method
    - Accept list of PackageMetadata instead of single ReleaseInfo
    - Generate pool directory paths using package_name (pool/main/{first_letter}/{package_name}/)
    - Generate Packages file entries for all packages
    - Include all Debian control fields from PackageMetadata
    - _Requirements: 2.1, 2.2, 2.5, 4.3, 4.4, 10.1, 10.2_
  
  - [ ] 11.2 Update Packages file generation
    - Generate entry for each package with all required fields
    - Use metadata from PackageMetadata (no .deb file reading)
    - Format: Package, Version, Architecture, Maintainer, Section, Priority, Homepage, Description, Filename, Size, MD5sum, SHA1, SHA256
    - _Requirements: 1.5, 9.6, 10.2_
  
  - [ ] 11.3 Update Release file generation
    - Include checksums (MD5, SHA1, SHA256) for Packages file
    - Include repository metadata (Origin, Label, Suite, Codename, Architectures, Components, Date, Valid-Until)
    - _Requirements: 10.3, 10.4_
  
  - [ ]* 11.4 Write property test for pool directory structure
    - **Property 7: Pool Directory Structure**
    - **Validates: Requirements 2.1, 2.5, 4.4, 11.1**
  
  - [ ]* 11.5 Write property test for Packages file entry completeness
    - **Property 8: Packages File Entry Completeness**
    - **Validates: Requirements 2.2, 2.6, 10.2**
  
  - [ ]* 11.6 Write property test for all packages included in Packages file
    - **Property 9: All Packages Included in Packages File**
    - **Validates: Requirements 4.3, 10.1**
  
  - [ ]* 11.7 Write property test for Release file checksums
    - **Property 13: Release File Contains Packages Checksums**
    - **Validates: Requirements 10.3**
  
  - [ ]* 11.8 Write property test for Release file metadata completeness
    - **Property 14: Release File Metadata Completeness**
    - **Validates: Requirements 10.4**
  
  - [ ]* 11.9 Write property test for package type agnostic metadata generation
    - **Property 22: Package Type Agnostic Metadata Generation**
    - **Validates: Requirements 17.5**

- [ ] 12. Update S3 publisher for multi-package support
  - [ ] 12.1 Update upload_repository method
    - Upload package files to pool directories based on package_name
    - Upload Packages file to dists/stable/main/binary-amd64/
    - Upload Release file to dists/stable/
    - Set Content-Type headers based on file type
    - Set public-read ACL on all files
    - _Requirements: 11.1, 11.2, 11.3, 11.6, 11.7_
  
  - [ ] 12.2 Implement upload_convenience_copy method
    - Accept PackageMetadata for latest kiro-repo package
    - Copy from pool directory to repository root (kiro-repo.deb)
    - Use S3 copy_object (no download/upload needed)
    - Set public-read ACL and appropriate Content-Type
    - Add metadata tags (version, package name)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 11.4_
  
  - [ ]* 12.3 Write property test for convenience copy points to latest version
    - **Property 10: Convenience Copy Points to Latest Version**
    - **Validates: Requirements 3.1, 3.3, 3.5**
  
  - [ ]* 12.4 Write property test for convenience copy location
    - **Property 11: Convenience Copy Location**
    - **Validates: Requirements 3.2, 11.4**
  
  - [ ]* 12.5 Write property test for convenience copy is regular object
    - **Property 12: Convenience Copy is Regular Object**
    - **Validates: Requirements 3.4**
  
  - [ ]* 12.6 Write property test for S3 upload path correctness
    - **Property 15: S3 Upload Path Correctness**
    - **Validates: Requirements 11.2, 11.3, 11.5**
  
  - [ ]* 12.7 Write property test for Content-Type headers
    - **Property 16: Content-Type Headers**
    - **Validates: Requirements 11.6**
  
  - [ ]* 12.8 Write property test for public read permissions
    - **Property 17: Public Read Permissions**
    - **Validates: Requirements 11.7**

- [ ] 13. Update main Lambda handler
  - [ ] 13.1 Update lambda_handler function
    - Add force_rebuild parameter support from event
    - Initialize PackageRouter instead of individual components
    - Call package_router.process_all_packages(force_rebuild)
    - Get all packages from VersionManager.get_all_packages()
    - Pass all packages to repository_builder.create_repository_structure()
    - Upload convenience copy of latest kiro-repo after repository upload
    - Find latest kiro-repo using version parsing
    - Call s3_publisher.upload_convenience_copy(latest_kiro_repo)
    - Update response messages for force_rebuild vs normal processing
    - _Requirements: 1.4, 7.1, 7.2, 7.3, 7.4, 7.5_
  
  - [ ]* 13.2 Write property test for force rebuild retrieves all packages
    - **Property 3: Force Rebuild Retrieves All Packages**
    - **Validates: Requirements 1.4, 7.2**
  
  - [ ]* 13.3 Write property test for repository metadata generation from DynamoDB alone
    - **Property 4: Repository Metadata Generation from DynamoDB Alone**
    - **Validates: Requirements 1.5, 9.6**
  
  - [ ]* 13.4 Write integration tests for complete workflows
    - Test normal processing workflow (new package detection, download, storage, repository build)
    - Test force rebuild workflow (skip version checking, use DynamoDB only)
    - Test error handling and recovery

- [ ] 14. Checkpoint - Verify core Lambda functionality
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. Create build script for kiro-repo package
  - [ ] 15.1 Create build script directory structure
    - Create `scripts/` directory
    - Create `templates/kiro-repo/` directory for Debian package templates
    - _Requirements: 5.1_
  
  - [ ] 15.2 Create Debian package templates
    - Create `templates/kiro-repo/DEBIAN/control` template with version placeholder
    - Create `templates/kiro-repo/DEBIAN/postinst` script to update APT sources
    - Create `templates/kiro-repo/DEBIAN/prerm` script to clean up on removal
    - Create `templates/kiro-repo/etc/apt/sources.list.d/kiro.list` template with repository URL
    - _Requirements: 5.1, 13.4, 13.5, 13.6_
  
  - [ ] 15.3 Implement build-kiro-repo.sh script
    - Accept version and environment parameters
    - Read Terraform state for S3 bucket, DynamoDB table, Lambda function names
    - Create Debian package directory structure
    - Generate control file with specified version
    - Copy postinst, prerm, and sources.list files
    - Use dpkg-deb to build .deb file
    - Compute SHA256, MD5, SHA1 checksums
    - Upload .deb to S3 staging area
    - Store complete PackageMetadata in DynamoDB
    - Invoke Lambda function with force_rebuild=true
    - Log each step with success/failure messages
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 8.1, 8.2, 8.3, 13.1, 13.2, 13.3, 13.7, 13.8, 13.9, 13.10_
  
  - [ ] 15.4 Add Terraform state reading logic
    - Parse terraform.tfstate or use terraform output command
    - Extract S3 bucket name, DynamoDB table name, Lambda function name
    - Handle missing state file with clear error message
    - Handle missing outputs with clear error message
    - Support environment parameter to read correct state file
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_
  
  - [ ]* 15.5 Write unit tests for build script components
    - Test Terraform state parsing
    - Test version increment logic
    - Test checksum computation
    - Test error handling for each step

- [ ] 16. Create DynamoDB schema migration script
  - [ ] 16.1 Implement DynamoDBSchemaMigration class
    - Create `scripts/migrate_dynamodb_schema.py`
    - Implement `__init__()` with environment and dry_run parameters
    - Initialize DynamoDB client and table reference
    - Initialize ConfigManager for metadata defaults
    - _Requirements: 15.1, 15.2_
  
  - [ ] 16.2 Implement backup phase
    - Implement `backup_existing_records()` method
    - Scan all existing records from DynamoDB
    - Export to JSONL file with timestamp
    - Verify backup file written successfully
    - Log count of records backed up
    - _Requirements: 15.2_
  
  - [ ] 16.3 Implement transformation phase
    - Implement `transform_records()` method
    - For each old record, create package_id field (package_name#version)
    - Add package_name field (default "kiro" for old records)
    - Add architecture field (default "amd64")
    - Add Debian metadata fields from PackageConfig
    - Add package_type field (default "external_download")
    - Preserve all existing fields
    - Validate each transformed record has required fields
    - _Requirements: 15.3, 15.4, 15.5, 15.12_
  
  - [ ] 16.4 Implement upload phase
    - Implement `upload_new_records()` method
    - Write each transformed record to DynamoDB with new schema
    - Use batch write operations for efficiency
    - Verify each write succeeds before proceeding
    - Log progress every 10 records
    - Skip if dry_run=True
    - _Requirements: 15.6_
  
  - [ ] 16.5 Implement cleanup phase
    - Implement `delete_old_records()` method
    - Delete old schema records after successful upload
    - Use batch delete operations
    - Verify deletions succeed
    - Log count of records deleted
    - Skip if dry_run=True
    - _Requirements: 15.7_
  
  - [ ] 16.6 Implement dry-run display
    - Implement `display_sample_transformations()` method
    - Show old and new record formats for first 3 records
    - Format output for easy verification
    - _Requirements: 15.8, 15.9_
  
  - [ ] 16.7 Implement command-line interface
    - Add argparse with --env, --dry-run, --backup-file arguments
    - Validate arguments (backup-file required for actual migration)
    - Implement main() function with error handling
    - Exit with non-zero status on failure
    - Preserve backup file on failure
    - _Requirements: 15.10, 15.11_
  
  - [ ]* 16.8 Write unit tests for migration script
    - Test record transformation logic
    - Test backup and restore operations
    - Test dry-run mode
    - Test error handling and rollback scenarios

- [ ] 17. Update instructions page
  - [ ] 17.1 Update index.html generation
    - Update `repository_builder.py` or create separate template
    - Explain kiro-repo.deb configures the repository
    - Provide command to download and install kiro-repo.deb from root
    - Explain that after installing kiro-repo, users can install kiro with apt
    - Explain that kiro-repo will be automatically updated by APT
    - Include manual configuration instructions as alternative
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_
  
  - [ ]* 17.2 Write unit tests for instructions page generation
    - Test HTML generation with correct content
    - Test all required sections present

- [ ] 18. Update error handling and logging
  - [ ] 18.1 Update error handling in PackageRouter
    - Wrap each package handler in try-catch
    - Log errors with package name and context
    - Continue processing other packages on failure
    - _Requirements: 14.3_
  
  - [ ] 18.2 Add structured logging for new operations
    - Log force_rebuild invocations with package count
    - Log convenience copy updates with old and new versions
    - Log package type routing decisions
    - Log configuration file loading
    - _Requirements: 14.4, 14.5_
  
  - [ ] 18.3 Add metadata validation logging
    - Log when package metadata is incomplete
    - Log which fields are missing
    - Log when packages are skipped due to missing metadata
    - _Requirements: 14.6_
  
  - [ ] 18.4 Update retry logic for DynamoDB and S3
    - Verify existing retry logic covers new operations
    - Add retry logic for S3 copy_object (convenience copy)
    - Add retry logic for new DynamoDB query patterns
    - _Requirements: 14.1, 14.2_

- [ ] 19. Update documentation
  - [ ] 19.1 Update README.md
    - Document multi-package support
    - Document force rebuild capability
    - Document build script usage for kiro-repo
    - Document migration script usage
    - _Requirements: 5.1, 7.1, 15.1_
  
  - [ ] 19.2 Create MIGRATION.md guide
    - Document migration process step-by-step
    - Document dry-run verification steps
    - Document rollback procedures
    - Document post-migration verification
    - _Requirements: 15.8, 15.9_
  
  - [ ] 19.3 Update deployment documentation
    - Document new configuration files
    - Document build script deployment
    - Document migration script execution
    - Document testing procedures

- [ ] 20. Final checkpoint - Integration testing
  - [ ] 20.1 Test complete workflow in dev environment
    - Deploy updated Lambda function
    - Run migration script in dry-run mode
    - Run migration script for actual migration
    - Verify existing kiro packages still work
    - Build and upload kiro-repo package
    - Verify kiro-repo appears in repository
    - Verify convenience copy at repository root
    - Test force rebuild functionality
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.7_
  
  - [ ] 20.2 Verify APT compatibility
    - Test apt update can parse repository
    - Test apt install kiro works
    - Test apt install kiro-repo works
    - Test apt upgrade detects kiro-repo updates
    - _Requirements: 2.3, 2.4, 12.2, 12.3, 20.5_
  
  - [ ] 20.3 Final verification and cleanup
    - Ensure all tests pass
    - Verify code coverage meets >80% target
    - Review all error handling paths
    - Ask the user if questions arise before production deployment

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at major milestones
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The migration script is a one-time operation that eliminates backward compatibility code
- Build script enables automated kiro-repo package deployment
- Force rebuild capability enables repository recovery and metadata updates without new packages
