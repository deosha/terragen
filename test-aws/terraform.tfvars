# AWS Configuration
aws_region = "us-east-1"

# Project Configuration
project_name = "terragen-s3"
environment  = "dev"

# S3 Bucket Configuration
bucket_name                = "" # Leave empty for auto-generated name
versioning_enabled         = true
encryption_algorithm       = "aws:kms"
enable_public_access_block = true
enable_logging             = true

# KMS Configuration
kms_key_deletion_window = 7

# Lifecycle Configuration
lifecycle_expiration_days                    = 0 # 0 = disabled
lifecycle_noncurrent_version_expiration_days = 90

# Additional Tags
tags = {
  Owner      = "DevOps Team"
  CostCenter = "Engineering"
  Compliance = "Required"
}