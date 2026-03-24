# CloudFront distribution for the Debian repository S3 website

resource "aws_cloudfront_distribution" "repository" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Kiro Debian Repository - ${var.env}"
  default_root_object = "index.html"

  aliases = [var.repo_url_domain]

  origin {
    domain_name = aws_s3_bucket_website_configuration.repository_website.website_endpoint
    origin_id   = "S3WebsiteOrigin"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "S3WebsiteOrigin"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 300
    max_ttl     = 3600
  }

  # Cache .deb and repo metadata files longer
  ordered_cache_behavior {
    path_pattern           = "*.deb"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "S3WebsiteOrigin"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 86400
    max_ttl     = 604800
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-cdn-${var.env}"
    Environment = var.env
  })
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.repository.domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.repository.id
}

output "repo_url" {
  description = "Public URL of the repository"
  value       = "https://${var.repo_url_domain}"
}

# CloudFront Standard Logging v2
# Uses CloudWatch vended logs delivery pipeline — no ACLs required.
# All three resources must be in us-east-1.

resource "aws_cloudwatch_log_delivery_source" "cloudfront_logs" {
  name         = "${var.project_name}-cf-logs-source-${var.env}"
  log_type     = "ACCESS_LOGS"
  resource_arn = aws_cloudfront_distribution.repository.arn
}

resource "aws_cloudwatch_log_delivery_destination" "cloudfront_logs" {
  name          = "${var.project_name}-cf-logs-destination-${var.env}"
  output_format = "w3c"

  delivery_destination_configuration {
    destination_resource_arn = aws_s3_bucket.cloudfront_logs.arn
  }
}

resource "aws_cloudwatch_log_delivery" "cloudfront_logs" {
  delivery_source_name     = aws_cloudwatch_log_delivery_source.cloudfront_logs.name
  delivery_destination_arn = aws_cloudwatch_log_delivery_destination.cloudfront_logs.arn

  s3_delivery_configuration {
    suffix_path                 = "/{yyyy}/{MM}/{dd}"
    enable_hive_compatible_path = false
  }
}
