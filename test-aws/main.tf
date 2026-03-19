# Generate random suffix for bucket name
resource "random_string" "bucket_suffix" {
  length  = 8
  lower   = true
  upper   = false
  special = false
}

# KMS key for S3 bucket encryption
resource "aws_kms_key" "s3_key" {
  count = var.encryption_algorithm == "aws:kms" ? 1 : 0

  description             = "KMS key for S3 bucket encryption - ${local.bucket_name}"
  deletion_window_in_days = var.kms_key_deletion_window
  enable_key_rotation     = true

  tags = merge(var.tags, {
    Name = "${var.project_name}-s3-kms-key"
  })
}

resource "aws_kms_alias" "s3_key_alias" {
  count = var.encryption_algorithm == "aws:kms" ? 1 : 0

  name          = "alias/${var.project_name}-s3-key-${var.environment}"
  target_key_id = aws_kms_key.s3_key[0].key_id
}

# Access logging bucket
resource "aws_s3_bucket" "access_logs" {
  count = var.enable_logging ? 1 : 0

  bucket = "${local.bucket_name}-access-logs"

  tags = merge(var.tags, {
    Name    = "${local.bucket_name}-access-logs"
    Purpose = "Access logs for main S3 bucket"
  })
}

resource "aws_s3_bucket_ownership_controls" "access_logs_ownership" {
  count = var.enable_logging ? 1 : 0

  bucket = aws_s3_bucket.access_logs[0].id

  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_acl" "access_logs_acl" {
  count = var.enable_logging ? 1 : 0

  depends_on = [aws_s3_bucket_ownership_controls.access_logs_ownership]
  bucket     = aws_s3_bucket.access_logs[0].id
  acl        = "log-delivery-write"
}

# Main S3 bucket
resource "aws_s3_bucket" "main" {
  bucket = local.bucket_name

  tags = merge(var.tags, {
    Name    = local.bucket_name
    Purpose = "Main S3 bucket with versioning and encryption"
  })
}

# S3 bucket versioning
resource "aws_s3_bucket_versioning" "main" {
  bucket = aws_s3_bucket.main.id

  versioning_configuration {
    status = var.versioning_enabled ? "Enabled" : "Disabled"
  }
}

# S3 bucket server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  bucket = aws_s3_bucket.main.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.encryption_algorithm
      kms_master_key_id = var.encryption_algorithm == "aws:kms" ? aws_kms_key.s3_key[0].arn : null
    }
    bucket_key_enabled = var.encryption_algorithm == "aws:kms" ? true : false
  }
}

# S3 bucket public access block
resource "aws_s3_bucket_public_access_block" "main" {
  count = var.enable_public_access_block ? 1 : 0

  bucket = aws_s3_bucket.main.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 bucket logging
resource "aws_s3_bucket_logging" "main" {
  count = var.enable_logging ? 1 : 0

  bucket = aws_s3_bucket.main.id

  target_bucket = aws_s3_bucket.access_logs[0].id
  target_prefix = "access-logs/"
}

# S3 bucket lifecycle configuration
resource "aws_s3_bucket_lifecycle_configuration" "main" {
  depends_on = [aws_s3_bucket_versioning.main]

  bucket = aws_s3_bucket.main.id

  rule {
    id     = "lifecycle_rule"
    status = "Enabled"

    filter {
      prefix = ""
    }

    dynamic "expiration" {
      for_each = var.lifecycle_expiration_days > 0 ? [1] : []
      content {
        days = var.lifecycle_expiration_days
      }
    }

    noncurrent_version_expiration {
      noncurrent_days = var.lifecycle_noncurrent_version_expiration_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# S3 bucket notification configuration (placeholder for future use)
resource "aws_s3_bucket_notification" "main" {
  bucket = aws_s3_bucket.main.id
}

# WAF Web ACL for CloudFront
resource "aws_wafv2_web_acl" "main" {
  count = var.enable_cloudfront && var.enable_waf ? 1 : 0

  name  = "${var.project_name}-${var.environment}-waf"
  scope = "CLOUDFRONT"

  default_action {
    allow {}
  }

  # AWS Managed Rules - Core Rule Set
  dynamic "rule" {
    for_each = var.waf_enable_aws_managed_rules ? [1] : []
    content {
      name     = "AWSManagedRulesCommonRuleSet"
      priority = 1

      override_action {
        none {}
      }

      statement {
        managed_rule_group_statement {
          name        = "AWSManagedRulesCommonRuleSet"
          vendor_name = "AWS"
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                 = "${var.project_name}-${var.environment}-CommonRuleSet"
        sampled_requests_enabled    = true
      }
    }
  }

  # AWS Managed Rules - Known Bad Inputs
  dynamic "rule" {
    for_each = var.waf_enable_aws_managed_rules ? [1] : []
    content {
      name     = "AWSManagedRulesKnownBadInputsRuleSet"
      priority = 2

      override_action {
        none {}
      }

      statement {
        managed_rule_group_statement {
          name        = "AWSManagedRulesKnownBadInputsRuleSet"
          vendor_name = "AWS"
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                 = "${var.project_name}-${var.environment}-KnownBadInputs"
        sampled_requests_enabled    = true
      }
    }
  }

  # Rate limiting rule
  dynamic "rule" {
    for_each = var.waf_enable_rate_limiting ? [1] : []
    content {
      name     = "RateLimitRule"
      priority = 3

      action {
        block {}
      }

      statement {
        rate_based_statement {
          limit              = var.waf_rate_limit
          aggregate_key_type = "IP"
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                 = "${var.project_name}-${var.environment}-RateLimit"
        sampled_requests_enabled    = true
      }
    }
  }

  # Geographic restriction rule
  dynamic "rule" {
    for_each = var.waf_enable_geo_restriction && (length(var.waf_blocked_countries) > 0 || length(var.waf_allowed_countries) > 0) ? [1] : []
    content {
      name     = "GeoRestrictionRule"
      priority = 4

      action {
        block {}
      }

      statement {
        geo_match_statement {
          country_codes = length(var.waf_allowed_countries) > 0 ? var.waf_allowed_countries : var.waf_blocked_countries
        }
      }

      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                 = "${var.project_name}-${var.environment}-GeoRestriction"
        sampled_requests_enabled    = true
      }
    }
  }

  tags = merge(var.tags, {
    Name    = "${var.project_name}-${var.environment}-waf"
    Purpose = "WAF for CloudFront distribution"
  })

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                 = "${var.project_name}-${var.environment}-waf"
    sampled_requests_enabled    = true
  }
}

# WAF Logging Configuration
resource "aws_cloudwatch_log_group" "waf_logs" {
  count = var.enable_cloudfront && var.enable_waf && var.waf_enable_logging ? 1 : 0

  name              = "/aws/wafv2/${var.project_name}-${var.environment}"
  retention_in_days = 30

  tags = merge(var.tags, {
    Name    = "${var.project_name}-${var.environment}-waf-logs"
    Purpose = "WAF request logs"
  })
}

resource "aws_wafv2_web_acl_logging_configuration" "main" {
  count = var.enable_cloudfront && var.enable_waf && var.waf_enable_logging ? 1 : 0

  resource_arn            = aws_wafv2_web_acl.main[0].arn
  log_destination_configs = [aws_cloudwatch_log_group.waf_logs[0].arn]

  redacted_fields {
    single_header {
      name = "authorization"
    }
  }

  redacted_fields {
    single_header {
      name = "cookie"
    }
  }

  depends_on = [aws_cloudwatch_log_group.waf_logs]
}

# CloudFront Origin Access Control
resource "aws_cloudfront_origin_access_control" "main" {
  count = var.enable_cloudfront ? 1 : 0

  name                              = "${var.project_name}-${var.environment}-oac"
  description                       = "Origin access control for ${local.bucket_name}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# S3 bucket policy for CloudFront
resource "aws_s3_bucket_policy" "cloudfront_access" {
  count = var.enable_cloudfront ? 1 : 0

  bucket = aws_s3_bucket.main.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipal"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.main.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.main[0].arn
          }
        }
      }
    ]
  })
}

# CloudFront distribution
resource "aws_cloudfront_distribution" "main" {
  count = var.enable_cloudfront ? 1 : 0

  origin {
    domain_name              = aws_s3_bucket.main.bucket_regional_domain_name
    origin_id                = "S3-${aws_s3_bucket.main.bucket}"
    origin_access_control_id = aws_cloudfront_origin_access_control.main[0].id
  }

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = var.cloudfront_default_root_object
  web_acl_id          = var.enable_waf ? aws_wafv2_web_acl.main[0].arn : null

  default_cache_behavior {
    allowed_methods  = var.cloudfront_allowed_methods
    cached_methods   = var.cloudfront_cached_methods
    target_origin_id = "S3-${aws_s3_bucket.main.bucket}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = var.cloudfront_viewer_protocol_policy
    min_ttl                = var.cloudfront_min_ttl
    default_ttl            = var.cloudfront_default_ttl
    max_ttl                = var.cloudfront_max_ttl
    compress               = var.cloudfront_compress
  }

  price_class = var.cloudfront_price_class

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = merge(var.tags, {
    Name    = "${var.project_name}-${var.environment}-cloudfront"
    Purpose = "CloudFront distribution for S3 bucket"
  })
}

locals {
  bucket_name = var.bucket_name != "" ? var.bucket_name : "${var.project_name}-${var.environment}-${random_string.bucket_suffix.result}"
}