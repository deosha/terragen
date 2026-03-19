# GCS Bucket with Versioning

This Terraform configuration creates a Google Cloud Storage (GCS) bucket with versioning enabled, along with associated security configurations and access logging.

## Features

- ✅ **Versioning Enabled**: Object versioning is enabled to maintain multiple versions of objects
- 🔒 **Security**: Uniform bucket-level access and public access prevention enforced
- 📊 **Logging**: Access logging to a separate coldline storage bucket
- 🏷️ **Lifecycle Management**: Configurable lifecycle rules for cost optimization
- 🔐 **IAM Integration**: Support for bucket-level IAM policies
- 📦 **Encryption**: Google-managed encryption at rest
- 🌐 **CORS Support**: CORS configuration for web applications
- 🏗️ **CI/CD Ready**: GitHub Actions workflows included

## Architecture

The configuration creates:

1. **Main GCS Bucket**: Primary storage bucket with versioning enabled
2. **Logs Bucket**: Coldline storage bucket for access logs
3. **IAM Bindings**: Optional IAM members for bucket access
4. **Lifecycle Rules**: Automated data lifecycle management

## Quick Start

### Prerequisites

- Google Cloud Project with billing enabled
- Service account with Storage Admin permissions
- Terraform >= 1.0 installed

### Usage

1. Clone this repository:
```bash
git clone <repository-url>
cd test-gcp
```

2. Update `terraform.tfvars` with your values:
```hcl
project_id  = "your-gcp-project-id"
bucket_name = "your-unique-bucket-name"
```

3. Initialize and apply:
```bash
terraform init
terraform plan
terraform apply
```

## Configuration

### Required Variables

| Variable | Description | Type |
|----------|-------------|------|
| `project_id` | GCP Project ID | string |
| `bucket_name` | Name for the GCS bucket | string |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `region` | GCP region | `us-central1` |
| `location` | Bucket location | `US-CENTRAL1` |
| `storage_class` | Storage class | `STANDARD` |
| `versioning_enabled` | Enable versioning | `true` |
| `uniform_bucket_level_access` | Enable uniform bucket-level access | `true` |
| `public_access_prevention` | Public access prevention | `enforced` |
| `force_destroy` | Allow bucket deletion with objects | `false` |

### Lifecycle Rules

Default lifecycle rules are configured:
- Delete objects after 365 days
- Delete archived (non-current) versions after 30 days

Customize by modifying the `lifecycle_rules` variable in `terraform.tfvars`.

### IAM Access

Add users or service accounts to bucket access:

```hcl
bucket_admins = [
  "user:admin@yourdomain.com",
  "serviceAccount:app@project.iam.gserviceaccount.com"
]

bucket_viewers = [
  "user:viewer@yourdomain.com"
]
```

## Security Features

- **Uniform Bucket-Level Access**: Simplifies access management
- **Public Access Prevention**: Prevents accidental public exposure
- **Encryption at Rest**: Google-managed encryption by default
- **Access Logging**: All bucket access is logged
- **IAM Integration**: Fine-grained access control

## Monitoring and Logging

- Access logs are stored in a separate coldline bucket
- Logs are automatically deleted after 90 days
- All resources are tagged for cost tracking

## CI/CD Integration

GitHub Actions workflows are included:

- **terraform.yml**: Main deployment workflow
- **pr-check.yml**: Pull request validation

### Setup CI/CD

1. Configure Workload Identity Federation:
```bash
# Create service account
gcloud iam service-accounts create terraform-ci

# Grant necessary permissions
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:terraform-ci@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.admin"
```

2. Set GitHub secrets:
- `WIF_PROVIDER`: Workload Identity Provider
- `WIF_SERVICE_ACCOUNT`: Service account email

## Outputs

| Output | Description |
|--------|-------------|
| `bucket_name` | Name of the created bucket |
| `bucket_url` | Bucket URL (gs://) |
| `bucket_self_link` | Full bucket URI |
| `versioning_enabled` | Versioning status |
| `logs_bucket_name` | Name of the logs bucket |

## Cost Optimization

- Logs bucket uses COLDLINE storage class
- Lifecycle rules automatically delete old data
- Default rules delete objects after 1 year
- Non-current versions deleted after 30 days

## Compliance

This configuration implements:
- Encryption at rest
- Access logging
- Public access prevention
- Uniform access policies

## Troubleshooting

### Common Issues

1. **Bucket name conflicts**: Bucket names must be globally unique
2. **Permission errors**: Ensure service account has Storage Admin role
3. **Region availability**: Verify chosen region supports all features

### Validation

```bash
# Format check
terraform fmt -check

# Validate configuration
terraform validate

# Security scan (if using tools like checkov)
checkov -f main.tf
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes and test
4. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review GCP documentation
3. Open an issue in the repository

---

## Version History

- **v1.0.0**: Initial release with basic GCS bucket and versioning
- Features: Versioning, logging, lifecycle management, IAM integration