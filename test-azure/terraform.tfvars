# Default variable values
location     = "eastus"
environment  = "dev"
project_name = "azurestorage"

# Storage configuration
storage_account_tier             = "Standard"
storage_account_replication_type = "LRS"
blob_container_access_type       = "private"

# Security and compliance settings
enable_versioning          = true
enable_change_feed         = true
soft_delete_retention_days = 30

# Tags
tags = {
  Environment = "dev"
  ManagedBy   = "terraform"
  Project     = "azure-blob-storage"
  Owner       = "infrastructure-team"
  CostCenter  = "engineering"
}