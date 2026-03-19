# Output Values
output "resource_group_name" {
  description = "Name of the resource group"
  value       = azurerm_resource_group.main.name
}

output "resource_group_location" {
  description = "Location of the resource group"
  value       = azurerm_resource_group.main.location
}

output "storage_account_name" {
  description = "Name of the storage account"
  value       = azurerm_storage_account.main.name
}

output "storage_account_id" {
  description = "ID of the storage account"
  value       = azurerm_storage_account.main.id
}

output "storage_account_primary_endpoint" {
  description = "Primary blob endpoint of the storage account"
  value       = azurerm_storage_account.main.primary_blob_endpoint
}

output "storage_account_primary_access_key" {
  description = "Primary access key of the storage account"
  value       = azurerm_storage_account.main.primary_access_key
  sensitive   = true
}

output "storage_account_primary_connection_string" {
  description = "Primary connection string of the storage account"
  value       = azurerm_storage_account.main.primary_connection_string
  sensitive   = true
}

output "blob_containers" {
  description = "List of blob container names"
  value = [
    azurerm_storage_container.data.name,
    azurerm_storage_container.logs.name,
    azurerm_storage_container.backups.name
  ]
}

output "key_vault_name" {
  description = "Name of the Key Vault"
  value       = azurerm_key_vault.main.name
}

output "key_vault_id" {
  description = "ID of the Key Vault"
  value       = azurerm_key_vault.main.id
}

output "key_vault_uri" {
  description = "URI of the Key Vault"
  value       = azurerm_key_vault.main.vault_uri
}

output "encryption_enabled" {
  description = "Whether encryption is enabled (always true for Azure Storage)"
  value       = true
}

output "https_only" {
  description = "Whether HTTPS-only traffic is enforced"
  value       = azurerm_storage_account.main.https_traffic_only_enabled
}

output "tls_version" {
  description = "Minimum TLS version enforced"
  value       = azurerm_storage_account.main.min_tls_version
}