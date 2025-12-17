# DynamoDB table for version tracking
resource "aws_dynamodb_table" "version_store" {
  name           = "${var.project_name}-versions-${var.env}"
  billing_mode   = "ON_DEMAND"
  hash_key       = "version"

  attribute {
    name = "version"
    type = "S"
  }

  # Enable point-in-time recovery
  point_in_time_recovery {
    enabled = true
  }

  # Server-side encryption
  server_side_encryption {
    enabled = true
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-versions-${var.env}"
    Environment = var.env
  })
}

# DynamoDB table outputs
output "dynamodb_table_name" {
  description = "Name of the DynamoDB table"
  value       = aws_dynamodb_table.version_store.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB table"
  value       = aws_dynamodb_table.version_store.arn
}