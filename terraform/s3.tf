# S3 bucket for hosting the debian repository
resource "aws_s3_bucket" "repository" {
  bucket = var.repo_bucket_name

  tags = merge(var.tags, {
    Name        = var.repo_bucket_name
    Environment = var.env
  })
}

# S3 bucket versioning
resource "aws_s3_bucket_versioning" "repository_versioning" {
  bucket = aws_s3_bucket.repository.id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3 bucket server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "repository_encryption" {
  bucket = aws_s3_bucket.repository.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# S3 bucket public access block (allow public read)
resource "aws_s3_bucket_public_access_block" "repository_pab" {
  bucket = aws_s3_bucket.repository.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

# S3 bucket policy for public read access
resource "aws_s3_bucket_policy" "repository_policy" {
  bucket = aws_s3_bucket.repository.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.repository.arn}/*"
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.repository_pab]
}

# S3 bucket CORS configuration for web access
resource "aws_s3_bucket_cors_configuration" "repository_cors" {
  bucket = aws_s3_bucket.repository.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# S3 bucket website configuration
resource "aws_s3_bucket_website_configuration" "repository_website" {
  bucket = aws_s3_bucket.repository.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "error.html"
  }
}

# S3 bucket lifecycle configuration
resource "aws_s3_bucket_lifecycle_configuration" "repository_lifecycle" {
  bucket = aws_s3_bucket.repository.id

  rule {
    id     = "cleanup_incomplete_multipart_uploads"
    status = "Enabled"

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  rule {
    id     = "transition_old_versions"
    status = "Enabled"

    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "STANDARD_IA"
    }

    noncurrent_version_transition {
      noncurrent_days = 90
      storage_class   = "GLACIER"
    }

    noncurrent_version_expiration {
      noncurrent_days = 365
    }
  }
}

# S3 bucket outputs
output "s3_bucket_name" {
  description = "Name of the S3 bucket"
  value       = aws_s3_bucket.repository.bucket
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket"
  value       = aws_s3_bucket.repository.arn
}

output "s3_bucket_website_endpoint" {
  description = "Website endpoint of the S3 bucket"
  value       = aws_s3_bucket_website_configuration.repository_website.website_endpoint
}

output "s3_bucket_domain_name" {
  description = "Domain name of the S3 bucket"
  value       = aws_s3_bucket.repository.bucket_domain_name
}