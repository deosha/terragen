# Generate a random string for unique naming
resource "random_string" "suffix" {
  length  = 8
  special = false
  upper   = false
}

# Create Resource Group
resource "azurerm_resource_group" "main" {
  name     = "${var.project_name}-${var.environment}-rg"
  location = var.location
  tags     = var.tags
}

# Create Storage Account with encryption
resource "azurerm_storage_account" "main" {
  name                     = "${var.project_name}${var.environment}${random_string.suffix.result}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = var.storage_account_tier
  account_replication_type = var.storage_account_replication_type
  account_kind             = "StorageV2"

  # Enable secure transfer (HTTPS only)
  https_traffic_only_enabled = true

  # Minimum TLS version
  min_tls_version = "TLS1_2"

  # Public access configuration
  public_network_access_enabled   = true
  allow_nested_items_to_be_public = false

  # Blob properties with versioning and soft delete
  blob_properties {
    versioning_enabled  = var.enable_versioning
    change_feed_enabled = var.enable_change_feed

    delete_retention_policy {
      days = var.soft_delete_retention_days
    }

    container_delete_retention_policy {
      days = var.soft_delete_retention_days
    }

    cors_rule {
      allowed_headers    = ["*"]
      allowed_methods    = ["GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS"]
      allowed_origins    = ["*"]
      exposed_headers    = ["*"]
      max_age_in_seconds = 3600
    }
  }

  # Network rules for security
  network_rules {
    default_action = "Allow"
    bypass         = ["AzureServices"]
  }

  tags = var.tags
}

# Create blob containers
resource "azurerm_storage_container" "data" {
  name                  = "data"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = var.blob_container_access_type
}

resource "azurerm_storage_container" "logs" {
  name                  = "logs"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = var.blob_container_access_type
}

resource "azurerm_storage_container" "backups" {
  name                  = "backups"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = var.blob_container_access_type
}

# Customer Managed Key for encryption (optional advanced encryption)
resource "azurerm_key_vault" "main" {
  name                = "${var.project_name}-${var.environment}-kv-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  enabled_for_disk_encryption     = true
  enabled_for_deployment          = true
  enabled_for_template_deployment = true
  purge_protection_enabled        = false
  soft_delete_retention_days      = 7

  tags = var.tags
}

# Get current client configuration
data "azurerm_client_config" "current" {}

# Key Vault access policy for current user/service principal
resource "azurerm_key_vault_access_policy" "current_user" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  key_permissions = [
    "Get", "List", "Create", "Delete", "Update", "Recover", "Purge", "GetRotationPolicy", "SetRotationPolicy"
  ]

  secret_permissions = [
    "Get", "List", "Set", "Delete", "Recover", "Purge"
  ]
}

# Storage Account Management Policy for lifecycle management
resource "azurerm_storage_management_policy" "main" {
  storage_account_id = azurerm_storage_account.main.id

  rule {
    name    = "default-lifecycle-rule"
    enabled = true

    filters {
      prefix_match = ["data/"]
      blob_types   = ["blockBlob"]
    }

    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than    = 30
        tier_to_archive_after_days_since_modification_greater_than = 90
        delete_after_days_since_modification_greater_than          = 365
      }

      snapshot {
        delete_after_days_since_creation_greater_than = 30
      }

      version {
        delete_after_days_since_creation = 30
      }
    }
  }
}