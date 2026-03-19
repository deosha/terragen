# TerraGen Default Security Policies
# These policies enforce security best practices for Terraform code.
# Uses OPA/Conftest Rego language.

package main

import future.keywords.in
import future.keywords.contains
import future.keywords.if

# =============================================================================
# S3 Bucket Security
# =============================================================================

# S3 buckets must have encryption enabled
deny contains msg if {
    resource := input.resource.aws_s3_bucket[name]
    not has_s3_encryption(name)
    msg := sprintf("S3 bucket '%s' is missing server-side encryption configuration", [name])
}

# Check for S3 encryption via aws_s3_bucket_server_side_encryption_configuration
# Handle array format from HCL2 parser
has_s3_encryption(bucket_name) if {
    # Config name matches bucket name
    some i
    _ := input.resource.aws_s3_bucket_server_side_encryption_configuration[bucket_name][i]
}

has_s3_encryption(bucket_name) if {
    # Check bucket reference contains the bucket name
    some name, i
    encryption := input.resource.aws_s3_bucket_server_side_encryption_configuration[name][i]
    contains(encryption.bucket, sprintf("aws_s3_bucket.%s", [bucket_name]))
}

# S3 buckets should have versioning enabled (warning)
warn contains msg if {
    resource := input.resource.aws_s3_bucket[name]
    not has_s3_versioning(name)
    msg := sprintf("S3 bucket '%s' does not have versioning enabled (recommended for data protection)", [name])
}

has_s3_versioning(bucket_name) if {
    # Config name matches bucket name (array format from HCL2 parser)
    some i, j
    versioning := input.resource.aws_s3_bucket_versioning[bucket_name][i]
    versioning.versioning_configuration[j].status == "Enabled"
}

has_s3_versioning(bucket_name) if {
    # Check bucket reference contains the bucket name
    some name, i, j
    versioning := input.resource.aws_s3_bucket_versioning[name][i]
    contains(versioning.bucket, sprintf("aws_s3_bucket.%s", [bucket_name]))
    versioning.versioning_configuration[j].status == "Enabled"
}

# S3 buckets should block public access
deny contains msg if {
    resource := input.resource.aws_s3_bucket[name]
    not has_public_access_block(name)
    msg := sprintf("S3 bucket '%s' is missing public access block configuration", [name])
}

has_public_access_block(bucket_name) if {
    # Config name matches bucket name (array format from HCL2 parser)
    some i
    block := input.resource.aws_s3_bucket_public_access_block[bucket_name][i]
    block.block_public_acls == true
    block.block_public_policy == true
}

has_public_access_block(bucket_name) if {
    # Check bucket reference contains the bucket name
    some name, i
    block := input.resource.aws_s3_bucket_public_access_block[name][i]
    contains(block.bucket, sprintf("aws_s3_bucket.%s", [bucket_name]))
    block.block_public_acls == true
    block.block_public_policy == true
}

# =============================================================================
# Security Group Rules
# =============================================================================

# Security groups should not allow unrestricted ingress from 0.0.0.0/0 on SSH
deny contains msg if {
    resource := input.resource.aws_security_group[name]
    some i
    ingress := resource.ingress[i]
    ingress.from_port <= 22
    ingress.to_port >= 22
    cidr_allows_all(ingress)
    msg := sprintf("Security group '%s' allows SSH (port 22) from 0.0.0.0/0", [name])
}

# Security groups should not allow unrestricted ingress from 0.0.0.0/0 on RDP
deny contains msg if {
    resource := input.resource.aws_security_group[name]
    some i
    ingress := resource.ingress[i]
    ingress.from_port <= 3389
    ingress.to_port >= 3389
    cidr_allows_all(ingress)
    msg := sprintf("Security group '%s' allows RDP (port 3389) from 0.0.0.0/0", [name])
}

# Security groups should not allow unrestricted ingress from 0.0.0.0/0 on database ports
deny contains msg if {
    resource := input.resource.aws_security_group[name]
    some i
    ingress := resource.ingress[i]
    is_database_port(ingress)
    cidr_allows_all(ingress)
    msg := sprintf("Security group '%s' allows database access from 0.0.0.0/0", [name])
}

# Check if any CIDR block allows all traffic
cidr_allows_all(rule) if {
    some j
    rule.cidr_blocks[j] == "0.0.0.0/0"
}

cidr_allows_all(rule) if {
    some j
    rule.ipv6_cidr_blocks[j] == "::/0"
}

# Check for common database ports
is_database_port(rule) if {
    ports := [3306, 5432, 1433, 27017, 6379]  # MySQL, PostgreSQL, MSSQL, MongoDB, Redis
    some port in ports
    rule.from_port <= port
    rule.to_port >= port
}

# Security group rules should have descriptions
warn contains msg if {
    resource := input.resource.aws_security_group_rule[name]
    not resource.description
    msg := sprintf("Security group rule '%s' is missing a description", [name])
}

# =============================================================================
# RDS Security
# =============================================================================

# RDS instances must have encryption enabled
deny contains msg if {
    resource := input.resource.aws_db_instance[name]
    not resource.storage_encrypted == true
    msg := sprintf("RDS instance '%s' does not have storage encryption enabled", [name])
}

# RDS instances should have deletion protection in production
warn contains msg if {
    resource := input.resource.aws_db_instance[name]
    not resource.deletion_protection == true
    msg := sprintf("RDS instance '%s' does not have deletion protection enabled", [name])
}

# RDS instances should have backup retention
warn contains msg if {
    resource := input.resource.aws_db_instance[name]
    not resource.backup_retention_period
    msg := sprintf("RDS instance '%s' does not have backup retention configured", [name])
}

warn contains msg if {
    resource := input.resource.aws_db_instance[name]
    resource.backup_retention_period == 0
    msg := sprintf("RDS instance '%s' has backup retention set to 0 days", [name])
}

# RDS instances should not be publicly accessible
deny contains msg if {
    resource := input.resource.aws_db_instance[name]
    resource.publicly_accessible == true
    msg := sprintf("RDS instance '%s' is publicly accessible", [name])
}

# =============================================================================
# EBS Volumes
# =============================================================================

# EBS volumes must be encrypted
deny contains msg if {
    resource := input.resource.aws_ebs_volume[name]
    not resource.encrypted == true
    msg := sprintf("EBS volume '%s' is not encrypted", [name])
}

# =============================================================================
# IAM Policies
# =============================================================================

# IAM policies should not use * for actions on sensitive services
warn contains msg if {
    resource := input.resource.aws_iam_policy[name]
    policy := json.unmarshal(resource.policy)
    some statement in policy.Statement
    statement.Effect == "Allow"
    statement.Action == "*"
    msg := sprintf("IAM policy '%s' grants overly permissive actions (*)", [name])
}

# IAM policies should not use * for resources on sensitive services
warn contains msg if {
    resource := input.resource.aws_iam_policy[name]
    policy := json.unmarshal(resource.policy)
    some statement in policy.Statement
    statement.Effect == "Allow"
    statement.Resource == "*"
    msg := sprintf("IAM policy '%s' grants access to all resources (*)", [name])
}

# =============================================================================
# EC2 Instances
# =============================================================================

# EC2 instances should have monitoring enabled
warn contains msg if {
    resource := input.resource.aws_instance[name]
    not resource.monitoring == true
    msg := sprintf("EC2 instance '%s' does not have detailed monitoring enabled", [name])
}

# EC2 instances should not have public IP by default
warn contains msg if {
    resource := input.resource.aws_instance[name]
    resource.associate_public_ip_address == true
    msg := sprintf("EC2 instance '%s' has a public IP address assigned", [name])
}

# =============================================================================
# CloudTrail
# =============================================================================

# CloudTrail should have encryption enabled
deny contains msg if {
    resource := input.resource.aws_cloudtrail[name]
    not resource.kms_key_id
    msg := sprintf("CloudTrail '%s' is not encrypted with KMS", [name])
}

# CloudTrail should have log file validation enabled
warn contains msg if {
    resource := input.resource.aws_cloudtrail[name]
    not resource.enable_log_file_validation == true
    msg := sprintf("CloudTrail '%s' does not have log file validation enabled", [name])
}

# =============================================================================
# Tags
# =============================================================================

# Resources should have required tags (configurable)
# Example: Require Name and Environment tags

# warn contains msg if {
#     resource := input.resource.aws_instance[name]
#     not resource.tags.Name
#     msg := sprintf("EC2 instance '%s' is missing required 'Name' tag", [name])
# }
#
# warn contains msg if {
#     resource := input.resource.aws_instance[name]
#     not resource.tags.Environment
#     msg := sprintf("EC2 instance '%s' is missing required 'Environment' tag", [name])
# }

# =============================================================================
# GCP Security (if using GCP provider)
# =============================================================================

# GCS buckets should have uniform bucket-level access
warn contains msg if {
    resource := input.resource.google_storage_bucket[name]
    not resource.uniform_bucket_level_access == true
    msg := sprintf("GCS bucket '%s' does not have uniform bucket-level access enabled", [name])
}

# GCE instances should not have public IP
warn contains msg if {
    resource := input.resource.google_compute_instance[name]
    some i
    access_config := resource.network_interface[_].access_config[i]
    msg := sprintf("GCE instance '%s' has a public IP address assigned", [name])
}

# =============================================================================
# Azure Security (if using Azure provider)
# =============================================================================

# Azure Storage accounts should use HTTPS only
deny contains msg if {
    resource := input.resource.azurerm_storage_account[name]
    not resource.enable_https_traffic_only == true
    msg := sprintf("Azure Storage account '%s' does not enforce HTTPS", [name])
}

# Azure SQL Database should have threat detection enabled
warn contains msg if {
    resource := input.resource.azurerm_sql_database[name]
    not has_threat_detection(name)
    msg := sprintf("Azure SQL Database '%s' does not have threat detection enabled", [name])
}

has_threat_detection(db_name) if {
    some name
    policy := input.resource.azurerm_sql_database_threat_detection_policy[name]
    policy.state == "Enabled"
}
