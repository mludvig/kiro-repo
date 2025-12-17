# Lambda function IAM role
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-role-${var.env}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(var.tags, {
    Name        = "${var.project_name}-lambda-role-${var.env}"
    Environment = var.env
  })
}

# Lambda function IAM policy
resource "aws_iam_role_policy" "lambda_policy" {
  name = "${var.project_name}-lambda-policy-${var.env}"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Scan",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.version_store.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:PutObjectAcl",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.repository.arn,
          "${aws_s3_bucket.repository.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = [
          aws_sns_topic.success_notifications.arn,
          aws_sns_topic.failure_notifications.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.dlq.arn
      }
    ]
  })
}

# Lambda deployment package (created by deploy.sh script)
# The deployment script creates a package with all dependencies included
locals {
  lambda_zip_path = "../build/${var.project_name}-${var.env}.zip"
}

# Lambda function
resource "aws_lambda_function" "debian_repo_manager" {
  filename         = local.lambda_zip_path
  function_name    = "${var.project_name}-${var.env}"
  role            = aws_iam_role.lambda_role.arn
  handler         = "main.lambda_handler"
  source_code_hash = filebase64sha256(local.lambda_zip_path)
  runtime         = "python3.12"
  timeout         = var.lambda_timeout
  memory_size     = var.lambda_memory_size

  ephemeral_storage {
    size = var.lambda_ephemeral_storage
  }

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.version_store.name
      S3_BUCKET_NAME      = aws_s3_bucket.repository.bucket
      LOG_LEVEL           = var.log_level
      SUCCESS_SNS_TOPIC   = aws_sns_topic.success_notifications.arn
      FAILURE_SNS_TOPIC   = aws_sns_topic.failure_notifications.arn
      ENVIRONMENT         = var.env
    }
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.dlq.arn
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.env}"
    Environment = var.env
  })

  depends_on = [
    aws_iam_role_policy.lambda_policy,
    aws_cloudwatch_log_group.lambda_logs
  ]
}

# CloudWatch Log Group for Lambda
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${var.project_name}-${var.env}"
  retention_in_days = 14

  tags = merge(var.tags, {
    Name        = "${var.project_name}-logs-${var.env}"
    Environment = var.env
  })
}

# Dead Letter Queue for failed Lambda executions
resource "aws_sqs_queue" "dlq" {
  name = "${var.project_name}-dlq-${var.env}"

  tags = merge(var.tags, {
    Name        = "${var.project_name}-dlq-${var.env}"
    Environment = var.env
  })
}

# Lambda function outputs
output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.debian_repo_manager.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.debian_repo_manager.arn
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda_role.arn
}