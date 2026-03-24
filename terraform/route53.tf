# Route53 DNS records for the CloudFront distribution

data "aws_route53_zone" "aws_nz" {
  name         = "aws.nz."
  private_zone = false
}

resource "aws_route53_record" "repository" {
  zone_id = data.aws_route53_zone.aws_nz.zone_id
  name    = var.repo_url_domain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.repository.domain_name
    zone_id                = aws_cloudfront_distribution.repository.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "repository_aaaa" {
  zone_id = data.aws_route53_zone.aws_nz.zone_id
  name    = var.repo_url_domain
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.repository.domain_name
    zone_id                = aws_cloudfront_distribution.repository.hosted_zone_id
    evaluate_target_health = false
  }
}

output "route53_record_fqdn" {
  description = "FQDN of the Route53 record"
  value       = aws_route53_record.repository.fqdn
}
