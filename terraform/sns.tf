# SNS topic for success notifications
resource "aws_sns_topic" "success_notifications" {
  name = "${var.project_name}-success-${var.env}"

  tags = merge(var.tags, {
    Name        = "${var.project_name}-success-${var.env}"
    Environment = var.env
  })
}

# SNS topic for failure notifications
resource "aws_sns_topic" "failure_notifications" {
  name = "${var.project_name}-failure-${var.env}"

  tags = merge(var.tags, {
    Name        = "${var.project_name}-failure-${var.env}"
    Environment = var.env
  })
}

# SNS topic subscription for success notifications (if email provided)
resource "aws_sns_topic_subscription" "success_email" {
  count = var.notification_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.success_notifications.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# SNS topic subscription for failure notifications (if email provided)
resource "aws_sns_topic_subscription" "failure_email" {
  count = var.notification_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.failure_notifications.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# SNS topic policy for Lambda to publish
resource "aws_sns_topic_policy" "success_notifications_policy" {
  arn = aws_sns_topic.success_notifications.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowLambdaPublish"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.lambda_role.arn
        }
        Action   = "sns:Publish"
        Resource = aws_sns_topic.success_notifications.arn
      }
    ]
  })
}

resource "aws_sns_topic_policy" "failure_notifications_policy" {
  arn = aws_sns_topic.failure_notifications.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowLambdaPublish"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.lambda_role.arn
        }
        Action   = "sns:Publish"
        Resource = aws_sns_topic.failure_notifications.arn
      },
      {
        Sid    = "AllowCloudWatchPublish"
        Effect = "Allow"
        Principal = {
          Service = "cloudwatch.amazonaws.com"
        }
        Action   = "sns:Publish"
        Resource = aws_sns_topic.failure_notifications.arn
      }
    ]
  })
}

# SNS outputs
output "success_sns_topic_arn" {
  description = "ARN of the success SNS topic"
  value       = aws_sns_topic.success_notifications.arn
}

output "failure_sns_topic_arn" {
  description = "ARN of the failure SNS topic"
  value       = aws_sns_topic.failure_notifications.arn
}