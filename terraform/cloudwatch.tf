# CloudWatch Events rule for periodic Lambda execution
resource "aws_cloudwatch_event_rule" "lambda_schedule" {
  name                = "${var.project_name}-schedule-${var.env}"
  description         = "Trigger Lambda function on schedule"
  schedule_expression = var.schedule_expression

  tags = merge(var.tags, {
    Name        = "${var.project_name}-schedule-${var.env}"
    Environment = var.env
  })
}

# CloudWatch Events target
resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.lambda_schedule.name
  target_id = "LambdaTarget"
  arn       = aws_lambda_function.debian_repo_manager.arn

  retry_policy {
    maximum_retry_attempts       = 2
    maximum_event_age_in_seconds = 3600
  }

  dead_letter_config {
    arn = aws_sqs_queue.dlq.arn
  }
}

# Lambda permission for CloudWatch Events
resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.debian_repo_manager.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.lambda_schedule.arn
}

# CloudWatch Alarm for Lambda errors
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.project_name}-lambda-errors-${var.env}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "This metric monitors lambda errors"
  alarm_actions       = [aws_sns_topic.failure_notifications.arn]

  dimensions = {
    FunctionName = aws_lambda_function.debian_repo_manager.function_name
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-lambda-errors-${var.env}"
    Environment = var.env
  })
}

# CloudWatch Alarm for Lambda duration
resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.project_name}-lambda-duration-${var.env}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Average"
  threshold           = "600000" # 10 minutes in milliseconds
  alarm_description   = "This metric monitors lambda duration"
  alarm_actions       = [aws_sns_topic.failure_notifications.arn]

  dimensions = {
    FunctionName = aws_lambda_function.debian_repo_manager.function_name
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-lambda-duration-${var.env}"
    Environment = var.env
  })
}

# CloudWatch Alarm for Lambda throttles
resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.project_name}-lambda-throttles-${var.env}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "This metric monitors lambda throttles"
  alarm_actions       = [aws_sns_topic.failure_notifications.arn]

  dimensions = {
    FunctionName = aws_lambda_function.debian_repo_manager.function_name
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-lambda-throttles-${var.env}"
    Environment = var.env
  })
}

# CloudWatch Alarm for DynamoDB throttles
resource "aws_cloudwatch_metric_alarm" "dynamodb_throttles" {
  count = var.enable_cloudwatch_alarms ? 1 : 0

  alarm_name          = "${var.project_name}-dynamodb-throttles-${var.env}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ThrottledRequests"
  namespace           = "AWS/DynamoDB"
  period              = "300"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "This metric monitors DynamoDB throttles"
  alarm_actions       = [aws_sns_topic.failure_notifications.arn]

  dimensions = {
    TableName = aws_dynamodb_table.version_store.name
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-dynamodb-throttles-${var.env}"
    Environment = var.env
  })
}

# CloudWatch Dashboard
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-${var.env}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.debian_repo_manager.function_name],
            [".", "Errors", ".", "."],
            [".", "Invocations", ".", "."]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "Lambda Metrics"
          period  = 300
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", aws_dynamodb_table.version_store.name],
            [".", "ConsumedWriteCapacityUnits", ".", "."],
            [".", "ThrottledRequests", ".", "."]
          ]
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          title   = "DynamoDB Metrics"
          period  = 300
        }
      }
    ]
  })
}

# CloudWatch outputs
output "cloudwatch_event_rule_arn" {
  description = "ARN of the CloudWatch Events rule"
  value       = aws_cloudwatch_event_rule.lambda_schedule.arn
}

output "cloudwatch_log_group_name" {
  description = "Name of the CloudWatch Log Group"
  value       = aws_cloudwatch_log_group.lambda_logs.name
}