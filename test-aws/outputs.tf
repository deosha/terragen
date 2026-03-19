output "bucket_name" {
  description = "Name of the S3 bucket"
  value       = aws_s3_bucket.main.bucket
}

output "bucket_arn" {
  description = "ARN of the S3 bucket"
  value       = aws_s3_bucket.main.arn
}

output "bucket_domain_name" {
  description = "Domain name of the S3 bucket"
  value       = aws_s3_bucket.main.bucket_domain_name
}

output "bucket_hosted_zone_id" {
  description = "Hosted zone ID of the S3 bucket"
  value       = aws_s3_bucket.main.hosted_zone_id
}

output "bucket_region" {
  description = "Region of the S3 bucket"
  value       = aws_s3_bucket.main.region
}

output "versioning_enabled" {
  description = "Whether versioning is enabled for the S3 bucket"
  value       = aws_s3_bucket_versioning.main.versioning_configuration[0].status == "Enabled"
}

output "encryption_algorithm" {
  description = "Server-side encryption algorithm used"
  value       = [for rule in aws_s3_bucket_server_side_encryption_configuration.main.rule : rule.apply_server_side_encryption_by_default[0].sse_algorithm][0]
}

output "kms_key_id" {
  description = "KMS key ID used for encryption (if KMS is used)"
  value       = var.encryption_algorithm == "aws:kms" ? aws_kms_key.s3_key[0].id : null
}

output "kms_key_arn" {
  description = "KMS key ARN used for encryption (if KMS is used)"
  value       = var.encryption_algorithm == "aws:kms" ? aws_kms_key.s3_key[0].arn : null
}

output "access_logs_bucket_name" {
  description = "Name of the access logs bucket"
  value       = var.enable_logging ? aws_s3_bucket.access_logs[0].bucket : null
}

output "public_access_blocked" {
  description = "Whether public access is blocked for the S3 bucket"
  value       = var.enable_public_access_block
}

# CloudFront outputs
output "cloudfront_distribution_id" {
  description = "ID of the CloudFront distribution"
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.main[0].id : null
}

output "cloudfront_distribution_arn" {
  description = "ARN of the CloudFront distribution"
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.main[0].arn : null
}

output "cloudfront_domain_name" {
  description = "Domain name of the CloudFront distribution"
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.main[0].domain_name : null
}

output "cloudfront_hosted_zone_id" {
  description = "Hosted zone ID of the CloudFront distribution"
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.main[0].hosted_zone_id : null
}

output "cloudfront_status" {
  description = "Current status of the CloudFront distribution"
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.main[0].status : null
}

output "cloudfront_origin_access_control_id" {
  description = "ID of the CloudFront Origin Access Control"
  value       = var.enable_cloudfront ? aws_cloudfront_origin_access_control.main[0].id : null
}

output "cloudfront_url" {
  description = "Full CloudFront distribution URL"
  value       = var.enable_cloudfront ? "https://${aws_cloudfront_distribution.main[0].domain_name}" : null
}

# WAF outputs
output "waf_web_acl_id" {
  description = "ID of the WAF Web ACL"
  value       = var.enable_cloudfront && var.enable_waf ? aws_wafv2_web_acl.main[0].id : null
}

output "waf_web_acl_arn" {
  description = "ARN of the WAF Web ACL"
  value       = var.enable_cloudfront && var.enable_waf ? aws_wafv2_web_acl.main[0].arn : null
}

output "waf_web_acl_name" {
  description = "Name of the WAF Web ACL"
  value       = var.enable_cloudfront && var.enable_waf ? aws_wafv2_web_acl.main[0].name : null
}

output "waf_cloudwatch_log_group" {
  description = "CloudWatch log group for WAF logs"
  value       = var.enable_cloudfront && var.enable_waf && var.waf_enable_logging ? aws_cloudwatch_log_group.waf_logs[0].name : null
}

output "waf_rate_limit" {
  description = "WAF rate limit configuration"
  value       = var.enable_cloudfront && var.enable_waf ? var.waf_rate_limit : null
}

output "waf_enabled" {
  description = "Whether WAF is enabled for CloudFront"
  value       = var.enable_cloudfront && var.enable_waf
}