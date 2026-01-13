# Product Overview

## Debian Repository Manager for Kiro IDE

This is an automated Debian repository manager that maintains a Debian package repository for Kiro IDE releases. The system runs as an AWS Lambda function that:

- Fetches the latest Kiro IDE release metadata from the official download endpoint
- Downloads new package versions (.deb files, certificates, and signatures)
- Maintains version tracking to avoid duplicate processing
- Builds and updates a complete Debian repository structure
- Publishes the repository to S3 for public access
- Provides comprehensive logging and monitoring

The system ensures that users can install and update Kiro IDE using standard Debian package management tools (`apt`, `dpkg`) by maintaining a properly structured APT repository.

## Key Features

- **Automated Processing**: Scheduled execution via CloudWatch Events
- **Version Tracking**: DynamoDB-based deduplication to avoid reprocessing
- **Security**: Package integrity verification with certificates and signatures
- **Monitoring**: Structured logging with CloudWatch integration
- **Infrastructure as Code**: Complete Terraform-managed AWS infrastructure