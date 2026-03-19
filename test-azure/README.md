# Azure Blob Storage with Encryption

This Terraform configuration creates a secure Azure Blob Storage environment with comprehensive encryption, security features, and best practices implemented.

## Architecture Overview

The infrastructure includes:
- **Resource Group**: Logical container for all resources
- **Storage Account**: Azure Storage V2 account with advanced security features
- **Blob Containers**: Multiple containers for different data types (data, logs, backups)
- **Key Vault**: For managing encryption keys and secrets
- **Lifecycle Management**: Automated tiering and deletion policies
- **Security Features**: HTTPS-only, minimum TLS 1.2, private access controls

## Security Features

### Encryption
- **Encryption at Rest**: All data is automatically encrypted using Microsoft-managed keys (256-bit AES)
- **Encryption in Transit**: HTTPS-only traffic enforced with minimum TLS 1.2
- **Key Management**: Azure Key Vault integration for advanced key management scenarios

### Access Controls
- **Private Blob Access**: Default container access is set to private
- **Network Security**: Network rules configured with secure defaults
- **Authentication**: Azure AD integration for secure access
- **RBAC**: Role-based access control ready

### Compliance & Monitoring
- **Soft Delete**: 30-day retention for accidentally deleted blobs
- **Versioning**: Blob versioning enabled for data protection
- **Change Feed**: Audit trail for all blob operations
- **Lifecycle Management**: Automated data tiering to optimize costs

## Quick Start

### Prerequisites
- [Terraform](https://www.terraform.io/downloads.html) >= 1.0
- [Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli) installed and configured
- Azure subscription with appropriate permissions

### Authentication
```bash
# Login to Azure
az login

# Set your subscription (if you have multiple)
az account set --subscription "your-subscription-id"
```

### Deployment
```bash
# Clone or download this configuration
cd test-azure

# Initialize Terraform
terraform init

# Review the planned changes
terraform plan

# Apply the configuration
terraform apply
```

## Configuration

### Variables
Key variables you can customize in `terraform.tfvars`:

```hcl
# Basic Configuration
location     = "eastus"           # Azure region
environment  = "dev"              # Environment name
project_name = "azurestorage"     # Project identifier

# Storage Configuration
storage_account_tier             = "Standard"  # Standard or Premium
storage_account_replication_type = "LRS"       # LRS, GRS, RAGRS, ZRS, GZRS, RAGZRS
blob_container_access_type       = "private"   # private, blob, or container

# Security Settings
enable_versioning           = true    # Enable blob versioning
enable_change_feed         = true    # Enable audit logging
soft_delete_retention_days = 30      # Days to retain deleted blobs

# Tags
tags = {
  Environment = "dev"
  ManagedBy   = "terraform"
  Project     = "azure-blob-storage"
  Owner       = "infrastructure-team"
  CostCenter  = "engineering"
}
```

### Outputs
After deployment, you'll receive:
- Storage account name and connection details
- Blob container names
- Key Vault information
- Security configuration status

## Storage Containers

Three containers are created by default:
- **data**: For application data storage
- **logs**: For log file storage  
- **backups**: For backup file storage

## Lifecycle Management

Automated policies are configured to:
- Move blobs to Cool tier after 30 days
- Move blobs to Archive tier after 90 days
- Delete blobs after 365 days
- Clean up blob snapshots after 30 days
- Remove old versions after 30 days

## Security Best Practices Implemented

✅ **Encryption at Rest**: Microsoft-managed keys (upgradable to customer-managed)\
✅ **Encryption in Transit**: HTTPS-only with TLS 1.2+\
✅ **Access Control**: Private container access by default\
✅ **Network Security**: Configurable network rules\
✅ **Monitoring**: Change feed and soft delete enabled\
✅ **Compliance**: Versioning and lifecycle policies\
✅ **Key Management**: Azure Key Vault integration\
✅ **Least Privilege**: Minimal required permissions

## CI/CD Pipeline

GitHub Actions workflow included for:
- **Code Quality**: Terraform formatting and validation
- **Security Scanning**: Checkov security analysis
- **Automated Planning**: PR-based terraform plan
- **Automated Deployment**: Main branch auto-deploy

### Setting up CI/CD
1. Add Azure credentials to GitHub Secrets:
   ```json
   AZURE_CREDENTIALS = {
     "clientId": "your-client-id",
     "clientSecret": "your-client-secret", 
     "subscriptionId": "your-subscription-id",
     "tenantId": "your-tenant-id"
   }
   ```

2. Enable GitHub Actions in your repository

3. Push changes to trigger the pipeline

## Cost Optimization

### Storage Tiers
- **Hot**: Frequently accessed data
- **Cool**: Infrequently accessed (30+ days)
- **Archive**: Rarely accessed (90+ days)

### Lifecycle Policies
Automatic tiering reduces costs by:
- Moving old data to cheaper storage tiers
- Deleting unnecessary old versions
- Removing expired snapshots

## Monitoring and Alerts

### Built-in Monitoring
- **Change Feed**: Track all blob operations
- **Soft Delete**: Recover accidentally deleted data
- **Versioning**: Track data changes over time

### Recommended Azure Monitor Alerts
- Storage account capacity thresholds
- Unusual access patterns
- Failed authentication attempts
- Network rule violations

## Backup and Recovery

### Automated Protection
- **Soft Delete**: 30-day recovery window
- **Blob Versioning**: Point-in-time recovery
- **Cross-Region Replication**: Available with GRS/RAGRS

### Manual Backup Options
- Azure Backup service integration
- Cross-region blob copy
- Point-in-time snapshots

## Troubleshooting

### Common Issues
1. **Authentication Errors**: Ensure Azure CLI is logged in
2. **Permission Denied**: Check Azure subscription permissions
3. **Resource Naming**: Storage account names must be globally unique
4. **Network Access**: Verify network rules if access is blocked

### Validation Commands
```bash
# Check Terraform syntax
terraform fmt -check -recursive

# Validate configuration
terraform validate

# Plan deployment
terraform plan

# Check Azure login
az account show
```

## Security Considerations

### Access Patterns
- Use Azure AD authentication when possible
- Implement shared access signatures (SAS) for temporary access
- Regular audit of access keys and permissions
- Enable logging for all operations

### Network Security
- Consider private endpoints for production environments
- Implement network service tags
- Use Azure Private Link for secure connectivity

## Advanced Configuration

### Customer-Managed Keys
For enhanced security, enable customer-managed encryption keys:
1. Create encryption key in Key Vault
2. Grant storage account access to Key Vault
3. Configure storage account to use customer key

### Private Endpoints
For isolated network access:
1. Create virtual network and subnet
2. Deploy private endpoint for blob storage
3. Configure DNS resolution

## Compliance

This configuration supports:
- **SOC 2**: Access controls and monitoring
- **HIPAA**: Encryption and audit logging
- **GDPR**: Data protection and retention policies
- **PCI DSS**: Secure data storage requirements

## Support

For issues or questions:
1. Check the [troubleshooting section](#troubleshooting)
2. Review Azure Storage documentation
3. Submit issues to your infrastructure team
4. Consult Azure support for platform issues

## License

This Terraform configuration is provided under the MIT License. See LICENSE file for details.