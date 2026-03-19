# AWS S3 Bucket with Versioning, Encryption, and CloudFront CDN

This Terraform configuration creates a production-ready AWS S3 bucket with versioning and encryption enabled, along with a CloudFront distribution for content delivery, security best practices, and comprehensive monitoring.

## Features

- **S3 Bucket with Versioning**: Main S3 bucket with versioning enabled/disabled via variable
- **Server-Side Encryption**: Supports both AES256 and AWS KMS encryption
- **KMS Key Management**: Dedicated KMS key with automatic rotation for encryption
- **CloudFront CDN**: Global content delivery network with Origin Access Control
- **Public Access Block**: Prevents public access to bucket contents
- **Access Logging**: Optional access logging to a separate bucket
- **Lifecycle Management**: Configurable lifecycle policies for cost optimization
- **Security Scanning**: Automated security scanning with TFSec and Checkov
- **CI/CD Pipeline**: GitHub Actions workflows for validation and deployment

## Architecture

```
┌─────────────────────────────────────────┐
│            CloudFront CDN               │
│  ┌─────────────────────────────────┐    │
│  │       Global Distribution       │    │
│  │      HTTPS Redirect Enabled     │    │
│  │       Caching & Compression     │    │
│  │      Origin Access Control      │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
                    │
                    │ Secure Access
                    ▼
┌─────────────────────────────────────────┐
│               Main S3 Bucket            │
│  ┌─────────────────────────────────┐    │
│  │        Versioning Enabled       │    │
│  │     KMS/AES256 Encryption       │    │
│  │      Public Access Blocked      │    │
│  │       Lifecycle Policies        │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
                    │
                    │ Access Logs
                    ▼
┌─────────────────────────────────────────┐
│           Access Logs Bucket            │
│  ┌─────────────────────────────────┐    │
│  │       Log Delivery Write        │    │
│  │         ACL Configured          │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
                    │
                    │ Encrypted with
                    ▼
┌─────────────────────────────────────────┐
│              KMS Key                    │
│  ┌─────────────────────────────────┐    │
│  │       Auto Key Rotation         │    │
│  │        7-day Deletion           │    │
│  │          Alias Created          │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## Usage

### Prerequisites

- AWS CLI configured with appropriate credentials
- Terraform >= 1.0
- Permissions to create S3 buckets, CloudFront distributions, KMS keys, and related resources

### Quick Start

1. **Clone and Initialize**
   ```bash
   cd /Users/deo/terragen/test-aws
   terraform init
   ```

2. **Review and Customize Variables**
   ```bash
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars with your desired values
   ```

3. **Plan and Apply**
   ```bash
   terraform plan
   terraform apply
   ```

### Configuration

#### Core Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `aws_region` | AWS region for resources | `us-east-1` | No |
| `project_name` | Name of the project | `terragen-s3` | No |
| `environment` | Environment (dev/staging/prod) | `dev` | No |
| `bucket_name` | S3 bucket name (auto-generated if empty) | `""` | No |
| `versioning_enabled` | Enable versioning | `true` | No |
| `encryption_algorithm` | Encryption type (AES256/aws:kms) | `aws:kms` | No |

#### Security Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `enable_public_access_block` | Block public access | `true` | No |
| `kms_key_deletion_window` | KMS key deletion window (days) | `7` | No |
| `enable_logging` | Enable access logging | `true` | No |

#### CloudFront Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `enable_cloudfront` | Enable CloudFront distribution | `true` | No |
| `cloudfront_price_class` | Price class (PriceClass_All/200/100) | `PriceClass_100` | No |
| `cloudfront_default_root_object` | Default root object | `index.html` | No |
| `cloudfront_viewer_protocol_policy` | Viewer protocol policy | `redirect-to-https` | No |
| `cloudfront_default_ttl` | Default TTL in seconds | `86400` | No |
| `cloudfront_min_ttl` | Minimum TTL in seconds | `0` | No |
| `cloudfront_max_ttl` | Maximum TTL in seconds | `31536000` | No |
| `cloudfront_compress` | Enable compression | `true` | No |

#### Lifecycle Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `lifecycle_expiration_days` | Days before object expiration (0=disabled) | `0` | No |
| `lifecycle_noncurrent_version_expiration_days` | Days before non-current version expiration | `90` | No |

### Examples

#### Basic S3 Bucket with CloudFront and KMS Encryption
```hcl
# terraform.tfvars
project_name = "my-webapp"
environment = "production"
versioning_enabled = true
encryption_algorithm = "aws:kms"
enable_public_access_block = true
enable_cloudfront = true
cloudfront_price_class = "PriceClass_All"
cloudfront_viewer_protocol_policy = "https-only"
```

#### S3 Bucket with CloudFront Disabled
```hcl
# terraform.tfvars
project_name = "internal-storage"
environment = "dev"
versioning_enabled = false
encryption_algorithm = "AES256"
enable_logging = false
enable_cloudfront = false
```

#### High-Performance Web Application Setup
```hcl
# terraform.tfvars
project_name = "high-performance-app"
environment = "prod"
versioning_enabled = true
encryption_algorithm = "aws:kms"
enable_cloudfront = true
cloudfront_price_class = "PriceClass_All"
cloudfront_default_ttl = 3600
cloudfront_max_ttl = 86400
cloudfront_compress = true
lifecycle_expiration_days = 730
```

## Outputs

| Output | Description |
|--------|-------------|
| `bucket_name` | Name of the created S3 bucket |
| `bucket_arn` | ARN of the S3 bucket |
| `bucket_domain_name` | Domain name of the S3 bucket |
| `versioning_enabled` | Whether versioning is enabled |
| `encryption_algorithm` | Encryption algorithm used |
| `kms_key_id` | KMS key ID (if KMS encryption) |
| `kms_key_arn` | KMS key ARN (if KMS encryption) |
| `access_logs_bucket_name` | Name of access logs bucket |
| `public_access_blocked` | Whether public access is blocked |
| **CloudFront Outputs** |  |
| `cloudfront_distribution_id` | CloudFront distribution ID |
| `cloudfront_distribution_arn` | CloudFront distribution ARN |
| `cloudfront_domain_name` | CloudFront domain name |
| `cloudfront_hosted_zone_id` | CloudFront hosted zone ID |
| `cloudfront_status` | CloudFront distribution status |
| `cloudfront_url` | Full CloudFront distribution URL |
| `cloudfront_origin_access_control_id` | Origin Access Control ID |

## Security Features

### Encryption
- **Server-side encryption** with AES256 or AWS KMS
- **KMS key rotation** enabled automatically
- **Bucket key** enabled for cost optimization with KMS

### Access Control
- **Public access blocked** by default for S3 bucket
- **Origin Access Control** for secure CloudFront-to-S3 access
- **HTTPS redirect** enforced via CloudFront
- **Bucket policy** restricting access to CloudFront only

### CloudFront Security
- **Origin Access Control (OAC)** replaces legacy OAI
- **Signed requests** using AWS SigV4
- **Viewer protocol policy** enforces HTTPS
- **Geographic restrictions** available via variables

### Monitoring & Logging
- **S3 access logging** to dedicated bucket
- **CloudFront logging** can be enabled
- **CloudTrail integration** ready
- **Cost optimization** via lifecycle policies

### Security Scanning
- **TFSec** for static analysis
- **Checkov** for compliance checks
- **SARIF reporting** for GitHub Security

## CloudFront Features

### Performance Optimization
- **Global edge locations** for low latency
- **HTTP/2 and IPv6** support enabled
- **GZIP compression** enabled by default
- **Configurable TTL** for different content types

### Caching Configuration
- **Default cache behavior** with customizable TTL
- **Query string forwarding** disabled by default
- **Cookie forwarding** disabled for better caching
- **Compression** enabled for better performance

### Price Classes
- `PriceClass_100`: US, Canada, Europe
- `PriceClass_200`: US, Canada, Europe, Asia, Middle East, Africa
- `PriceClass_All`: All CloudFront edge locations

## CI/CD Pipeline

### GitHub Actions Workflows

1. **Terraform Validation** (`.github/workflows/terraform.yml`)
   - Format checking
   - Syntax validation
   - Plan generation
   - Automated apply on main branch

2. **Security Scanning** (`.github/workflows/security-scan.yml`)
   - TFSec security analysis
   - Checkov compliance checks
   - SARIF report generation

### Required Secrets

Add these secrets to your GitHub repository:

```
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
```

## Best Practices Implemented

### Security
- ✅ No hardcoded credentials
- ✅ Encryption at rest enabled
- ✅ Public access blocked for S3
- ✅ Origin Access Control for CloudFront
- ✅ HTTPS enforcement
- ✅ Security scanning automation

### Performance
- ✅ CloudFront global CDN
- ✅ Compression enabled
- ✅ Optimized caching policies
- ✅ HTTP/2 and IPv6 support

### Reliability
- ✅ Versioning enabled
- ✅ Lifecycle management
- ✅ Error handling
- ✅ Resource dependencies

### Maintainability
- ✅ Modular configuration
- ✅ Comprehensive documentation
- ✅ Variable validation
- ✅ Consistent tagging

### Cost Optimization
- ✅ Lifecycle policies
- ✅ KMS bucket keys
- ✅ CloudFront price classes
- ✅ Configurable TTL settings

## Troubleshooting

### Common Issues

1. **Bucket Name Conflicts**
   ```
   Error: BucketAlreadyExists
   ```
   **Solution**: Set a unique `bucket_name` or use auto-generated names

2. **CloudFront Distribution Takes Time**
   ```
   CloudFront distribution deployment can take 15-20 minutes
   ```
   **Solution**: This is normal behavior for CloudFront distributions

3. **Origin Access Control Setup**
   ```
   Error: S3 bucket policy conflicts
   ```
   **Solution**: Ensure no conflicting bucket policies exist

4. **KMS Permissions**
   ```
   Error: AccessDenied for KMS operations
   ```
   **Solution**: Ensure IAM user has KMS permissions

### Validation Commands

```bash
# Format check
terraform fmt -check -recursive

# Syntax validation
terraform validate

# Security scan
tfsec .
checkov -d . --framework terraform

# Plan review
terraform plan -out=tfplan
terraform show tfplan
```

## Performance Testing

After deployment, test your CloudFront distribution:

```bash
# Test CloudFront URL
curl -I https://YOUR_CLOUDFRONT_DOMAIN/

# Test caching headers
curl -I -H "Cache-Control: no-cache" https://YOUR_CLOUDFRONT_DOMAIN/

# Performance testing with multiple locations
# Use tools like curl, wget, or online testing services
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run validation tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For questions or issues:
1. Check the troubleshooting section
2. Review GitHub Issues
3. Create a new issue with detailed information

---

**Generated by TerraGen** - Infrastructure as Code made simple.