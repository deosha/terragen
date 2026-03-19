variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "terragen-s3"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "bucket_name" {
  description = "Name of the S3 bucket (leave empty for auto-generated name)"
  type        = string
  default     = ""
}

variable "versioning_enabled" {
  description = "Enable versioning for the S3 bucket"
  type        = bool
  default     = true
}

variable "encryption_algorithm" {
  description = "Server-side encryption algorithm (AES256 or aws:kms)"
  type        = string
  default     = "aws:kms"
  validation {
    condition     = contains(["AES256", "aws:kms"], var.encryption_algorithm)
    error_message = "Encryption algorithm must be either 'AES256' or 'aws:kms'."
  }
}

variable "kms_key_deletion_window" {
  description = "KMS key deletion window in days"
  type        = number
  default     = 7
}

variable "enable_public_access_block" {
  description = "Enable public access block for the S3 bucket"
  type        = bool
  default     = true
}

variable "enable_logging" {
  description = "Enable access logging for the S3 bucket"
  type        = bool
  default     = true
}

variable "lifecycle_expiration_days" {
  description = "Number of days after which objects expire (0 to disable)"
  type        = number
  default     = 0
}

variable "lifecycle_noncurrent_version_expiration_days" {
  description = "Number of days after which non-current versions expire"
  type        = number
  default     = 90
}

variable "tags" {
  description = "Additional tags to apply to resources"
  type        = map(string)
  default     = {}
}

# CloudFront variables
variable "enable_cloudfront" {
  description = "Enable CloudFront distribution for the S3 bucket"
  type        = bool
  default     = true
}

variable "cloudfront_price_class" {
  description = "CloudFront distribution price class"
  type        = string
  default     = "PriceClass_100"
  validation {
    condition     = contains(["PriceClass_All", "PriceClass_200", "PriceClass_100"], var.cloudfront_price_class)
    error_message = "Price class must be one of: PriceClass_All, PriceClass_200, PriceClass_100."
  }
}

variable "cloudfront_default_root_object" {
  description = "Default root object for CloudFront distribution"
  type        = string
  default     = "index.html"
}

variable "cloudfront_viewer_protocol_policy" {
  description = "CloudFront viewer protocol policy"
  type        = string
  default     = "redirect-to-https"
  validation {
    condition     = contains(["allow-all", "https-only", "redirect-to-https"], var.cloudfront_viewer_protocol_policy)
    error_message = "Viewer protocol policy must be one of: allow-all, https-only, redirect-to-https."
  }
}

variable "cloudfront_allowed_methods" {
  description = "CloudFront allowed methods"
  type        = list(string)
  default     = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
}

variable "cloudfront_cached_methods" {
  description = "CloudFront cached methods"
  type        = list(string)
  default     = ["GET", "HEAD"]
}

variable "cloudfront_default_ttl" {
  description = "CloudFront default TTL in seconds"
  type        = number
  default     = 86400
}

variable "cloudfront_min_ttl" {
  description = "CloudFront minimum TTL in seconds"
  type        = number
  default     = 0
}

variable "cloudfront_max_ttl" {
  description = "CloudFront maximum TTL in seconds"
  type        = number
  default     = 31536000
}

variable "cloudfront_compress" {
  description = "Enable CloudFront compression"
  type        = bool
  default     = true
}

# WAF variables
variable "enable_waf" {
  description = "Enable WAF for CloudFront distribution"
  type        = bool
  default     = true
}

variable "waf_rate_limit" {
  description = "Rate limit for WAF (requests per 5 minutes from a single IP)"
  type        = number
  default     = 2000
}

variable "waf_blocked_countries" {
  description = "List of country codes to block (e.g., ['CN', 'RU'])"
  type        = list(string)
  default     = []
}

variable "waf_allowed_countries" {
  description = "List of country codes to allow (empty means allow all, overrides blocked_countries)"
  type        = list(string)
  default     = []
}

variable "waf_enable_aws_managed_rules" {
  description = "Enable AWS managed rule sets for WAF"
  type        = bool
  default     = true
}

variable "waf_enable_rate_limiting" {
  description = "Enable rate limiting rule in WAF"
  type        = bool
  default     = true
}

variable "waf_enable_geo_restriction" {
  description = "Enable geographic restriction in WAF"
  type        = bool
  default     = false
}

variable "waf_enable_logging" {
  description = "Enable WAF request logging to CloudWatch"
  type        = bool
  default     = true
}