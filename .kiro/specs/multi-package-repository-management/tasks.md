# Implementation Plan: Multi-Package Repository Management

## Overview

This implementation extends the Debian Repository Manager to support multiple packages (kiro, kiro-repo, kiro-cli) with DynamoDB as the single source of truth. The implementation includes schema migration, configuration management, enhanced Lambda functionality, and an improved build script.

## Tasks

- [x] 1. Create DynamoDB schema migration script
  - Create scripts/migrate-dynamodb-to-package-name.py
  - Implement table name reading from Terraform state
  - Implement item migration logic (add package_name, package_id, architecture, metadata fields)
  - Make migration idempotent - only update items missing required fields
  - Add dry-run mode for safe testing
  - Add comprehensive error handling and progress reporting
  - Report skipped items (already migrated) vs migrated items
  - Test migration script with sample data
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ]* 1.1 Write property test for migration completeness
  - **Property 1: Migration Completeness**
  - **Validates: Requirements 7.1, 7.3**

- [x] 2. Update PackageMetadata data model for new schema
  - Update src/models.py to add package_name field
  - Update src/models.py to add package_id field (computed from package_name and version)
  - Add architecture field
  - Add Debian metadata fields (section, priority, maintainer, homepage, description, depends)
  - Make certificate_url, signature_url, and notes optional
  - Update from_metadata() class method to set package_name="kiro" for existing kiro packages
  - Run ruff check and format before completion
  - _Requirements: 1.1, 7.1, 7.4_

- [ ]* 2.1 Write property test for package name field presence
  - **Property 1: Package Name Field Presence**
  - **Validates: Requirements 1.1, 7.1**

- [ ]* 2.2 Write property test for optional field support
  - **Property 10: Optional Field Support**
  - **Validates: Requirements 7.4**

- [x] 3. Update VersionManager to support new schema
  - Update src/version_manager.py to use package_id as key
  - Implement get_all_packages() to retrieve all packages
  - Implement get_packages_by_name() to filter by package name
  - Update store_package_metadata() to include new fields (package_name, package_id, architecture, metadata)
  - Update is_package_version_processed() to use package_name and version
  - Update DynamoDB queries to use new schema
  - Ensure backward compatibility: if package_name is missing, assume "kiro"
  - Run ruff check and format before completion
  - _Requirements: 1.1, 1.2, 1.5, 6.1, 7.1, 7.3_

- [ ]* 3.1 Write property test for multi-package query completeness
  - **Property 2: Multi-Package Query Completeness**
  - **Validates: Requirements 1.2, 1.5, 6.1**

- [x] 4. Update RepositoryBuilder for multi-package support
  - Update src/repository_builder.py to handle multiple packages
  - Update generate_packages_file() to include all packages
  - Implement generate_package_entry() for package-specific metadata
  - Update pool directory organization to use package names
  - Ensure all package versions are included
  - Run ruff check and format before completion
  - _Requirements: 1.5, 6.2, 6.3, 6.4, 6.5_

- [ ]* 4.1 Write property test for multi-package repository generation
  - **Property 8: Multi-Package Repository Generation**
  - **Validates: Requirements 6.2, 6.3**

- [ ]* 4.2 Write property test for package organization and versioning
  - **Property 9: Package Organization and Versioning**
  - **Validates: Requirements 6.4, 6.5**

- [x] 5. Update Lambda main handler for new schema
  - Update src/main.py to query all packages from DynamoDB
  - Ensure repository building uses only DynamoDB data (no S3 reads)
  - Update force rebuild logic to include all packages
  - Ensure new kiro packages are stored with package_name="kiro" and package_id
  - Run ruff check and format before completion
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 6.1, 6.2_

- [ ]* 5.1 Write property test for DynamoDB-only repository building
  - **Property 3: DynamoDB-Only Repository Building**
  - **Validates: Requirements 1.3, 1.4**

- [ ] 6. Deploy updated Lambda code
  - Deploy Lambda with updated schema support to dev environment
  - Verify Lambda can read existing data (backward compatibility)
  - Verify Lambda writes new data with new schema fields
  - Deploy Lambda to prod environment
  - _Requirements: 1.1, 7.1_

- [ ] 7. Checkpoint - Verify Lambda compatibility
  - Trigger Lambda execution in dev
  - Verify it processes existing data correctly
  - Verify new packages are stored with new schema
  - Ask user if questions arise

- [ ] 8. Run DynamoDB migration
  - Create backup of dev DynamoDB table
  - Run migration script on dev environment
  - Verify all items have new fields
  - Trigger force rebuild on dev
  - Verify dev repository includes all packages
  - Create backup of prod DynamoDB table
  - Run migration script on prod environment
  - Trigger force rebuild on prod
  - Verify prod repository includes all packages
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 9. Create kiro-repo-deb directory structure and configuration
- [ ] 9. Create kiro-repo-deb directory structure and configuration
  - Create kiro-repo-deb/ directory with subdirectories (config/, scripts/, templates/)
  - Create JSON schema for configuration validation (config/schema.json)
  - Create dev.json and prod.json configuration files
  - Create control file template (templates/control.template)
  - Create postinst script template (templates/postinst.template)
  - Create README.md with usage instructions
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ]* 9.1 Write property test for configuration file validity
  - **Property 4: Configuration File Validity**
  - **Validates: Requirements 2.1, 2.2, 2.5, 9.1, 9.3, 9.4**

- [ ] 10. Implement configuration manager module
  - Create src/config_manager.py
  - Implement load_config() to read JSON/YAML files
  - Implement validate_config() with schema validation
  - Implement get_environment_config() for env-specific configs
  - Add URL format validation
  - Add semantic version validation
  - Run ruff check and format before completion
  - _Requirements: 2.2, 2.3, 2.5, 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ]* 10.1 Write property test for configuration validation
  - **Property 11: Configuration Validation Early Exit**
  - **Validates: Requirements 9.5**

- [ ] 11. Implement Terraform state reader module
  - Create src/terraform_state_reader.py
  - Implement get_dynamodb_table_name() to read from Terraform state
  - Implement get_lambda_function_arn() for force rebuild triggering
  - Implement get_s3_bucket_name() for S3 operations
  - Add error handling for missing state files
  - Add environment parameter support (dev/prod)
  - Run ruff check and format before completion
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ]* 11.1 Write property test for Terraform state table resolution
  - **Property 6: Terraform State Table Resolution**
  - **Validates: Requirements 4.1, 4.2, 4.4**

- [ ] 12. Create enhanced build script for kiro-repo
  - Create kiro-repo-deb/scripts/build.sh
  - Implement configuration loading from JSON file
  - Implement configuration validation
  - Implement Debian package building (control, postinst, sources.list.d)
  - Implement S3 upload with public read permissions
  - Implement DynamoDB metadata recording
  - Implement force rebuild triggering via Lambda
  - Add comprehensive logging for all operations
  - Add error handling with clear messages
  - Run shellcheck for validation
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.2, 5.3, 5.4, 5.5, 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ]* 12.1 Write property test for upload and record workflow
  - **Property 5: Upload and Record Workflow**
  - **Validates: Requirements 3.1, 3.2, 3.3, 3.5**

- [ ]* 12.2 Write property test for force rebuild triggering
  - **Property 7: Force Rebuild Triggering**
  - **Validates: Requirements 5.1, 5.2, 5.3**

- [ ] 13. Create example kiro-repo configuration files
  - Create kiro-repo-deb/config/dev.json with dev settings
  - Create kiro-repo-deb/config/prod.json with prod settings
  - Validate configurations against schema
  - _Requirements: 2.1, 2.2, 2.3, 2.5_

- [ ] 14. Test kiro-repo build and upload workflow
  - Build kiro-repo package for dev using configuration
  - Verify package structure and metadata
  - Upload to S3 and record in DynamoDB
  - Trigger force rebuild
  - Verify repository includes kiro-repo package
  - Test installation on a clean system
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.2, 5.3_

- [ ] 15. Update documentation
  - Update BUILD_KIRO_REPO.md with new workflow
  - Document configuration file format
  - Document migration process
  - Document multi-package support
  - Add examples for adding new packages
  - _Requirements: 8.5_

- [ ] 16. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- **CRITICAL**: Lambda code must be updated (tasks 2-6) and deployed BEFORE running migration (task 8)
- Migration must be completed before deploying kiro-repo build functionality
- **Migration is idempotent**: Can be run multiple times safely - only updates items missing fields
- Configuration files should be version controlled
- Build script should be tested in dev before running in prod
- Each package can have different metadata requirements
- The system automatically handles new packages without code changes
- Lambda includes backward compatibility to read old schema during migration period
