"""
Security rules for prompt engineering - teaches LLM to generate compliant code from the start.

These rules are derived from:
- tfsec (Aqua Security)
- Checkov (Bridgecrew/Prisma)
- CIS Benchmarks
- AWS/GCP/Azure Well-Architected Frameworks
"""

from pathlib import Path
from typing import Optional


# Common security rules across all providers
COMMON_RULES = """
## General Security Rules (ALL PROVIDERS)

### Encryption
- ALWAYS enable encryption at rest for all storage (buckets, disks, databases)
- Use provider-managed keys (SSE-S3, Google-managed, Azure-managed) at minimum
- For sensitive data, use customer-managed keys (KMS/Cloud KMS/Key Vault)
- Enable encryption in transit (TLS/SSL) for all data transfers

### Network Security
- NEVER use 0.0.0.0/0 for ingress rules on sensitive ports (22, 3389, 1433, 3306, 5432, 27017)
- Use specific CIDR ranges or security group/firewall references
- Place databases and internal services in private subnets only
- Use NAT gateways for outbound internet access from private subnets
- Enable VPC Flow Logs / Network Watcher for traffic monitoring
- Restrict egress rules to required destinations only

### Access Control
- Implement least-privilege IAM policies - never use wildcard (*) for actions or resources
- Use service accounts / managed identities instead of access keys where possible
- Enable MFA for all human user accounts
- Rotate credentials regularly (define rotation policies)
- Use IAM roles for service-to-service authentication

### Logging & Monitoring
- Enable access logging for all storage buckets
- Enable audit logging (CloudTrail/Cloud Audit/Activity Log)
- Send logs to centralized logging (CloudWatch/Stackdriver/Log Analytics)
- Enable deletion protection for production databases
- Set up alerting for security events

### Resource Configuration
- Tag all resources with: Environment, Owner, CostCenter, Application
- Enable versioning for object storage
- Set lifecycle policies for log retention
- Use private endpoints for managed services where available
- Disable public access by default
"""

AWS_RULES = """
## AWS-Specific Security Rules (tfsec + Checkov)

### S3 Buckets (CRITICAL)
```hcl
resource "aws_s3_bucket" "example" {
  bucket = "my-bucket"
}

# REQUIRED: Block all public access
resource "aws_s3_bucket_public_access_block" "example" {
  bucket = aws_s3_bucket.example.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# REQUIRED: Enable encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "example" {
  bucket = aws_s3_bucket.example.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"  # or "AES256"
    }
  }
}

# REQUIRED: Enable versioning
resource "aws_s3_bucket_versioning" "example" {
  bucket = aws_s3_bucket.example.id
  versioning_configuration {
    status = "Enabled"
  }
}

# RECOMMENDED: Enable logging
resource "aws_s3_bucket_logging" "example" {
  bucket = aws_s3_bucket.example.id
  target_bucket = aws_s3_bucket.logs.id
  target_prefix = "s3-access-logs/"
}
```

### Security Groups (CRITICAL)
```hcl
# WRONG - Never do this:
# cidr_blocks = ["0.0.0.0/0"]  # for SSH, RDP, database ports

# CORRECT - Use specific CIDRs or security group references:
resource "aws_security_group" "example" {
  name        = "example"
  description = "Example security group"  # REQUIRED: Add description
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "HTTPS from VPC"  # REQUIRED: Add description
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    cidr_blocks     = [aws_vpc.main.cidr_block]  # VPC CIDR only
  }

  egress {
    description = "Allow outbound to VPC"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [aws_vpc.main.cidr_block]  # Restrict egress
  }
}
```

### EKS Clusters (CRITICAL)
```hcl
resource "aws_eks_cluster" "example" {
  name     = "example"
  role_arn = aws_iam_role.cluster.arn

  vpc_config {
    endpoint_private_access = true   # REQUIRED: Enable private access
    endpoint_public_access  = false  # RECOMMENDED: Disable public access
    # If public access needed, restrict CIDRs:
    # public_access_cidrs = ["10.0.0.0/8"]  # NOT 0.0.0.0/0
  }

  # REQUIRED: Enable control plane logging
  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  # REQUIRED: Enable secrets encryption
  encryption_config {
    provider {
      key_arn = aws_kms_key.eks.arn
    }
    resources = ["secrets"]
  }
}
```

### RDS Databases (CRITICAL)
```hcl
resource "aws_db_instance" "example" {
  # REQUIRED: Enable encryption
  storage_encrypted = true
  kms_key_id        = aws_kms_key.rds.arn  # Optional but recommended

  # REQUIRED: Disable public accessibility
  publicly_accessible = false

  # REQUIRED for production: Enable deletion protection
  deletion_protection = true

  # REQUIRED: Enable automated backups
  backup_retention_period = 7  # At least 1 day

  # RECOMMENDED: Multi-AZ for production
  multi_az = true

  # REQUIRED: Use private subnet group
  db_subnet_group_name = aws_db_subnet_group.private.name

  # RECOMMENDED: Enable Performance Insights
  performance_insights_enabled = true
}
```

### VPC Configuration (CRITICAL - ALWAYS CREATE)
```hcl
# MANDATORY: Enable VPC Flow Logs - This is REQUIRED for all VPCs
# Without flow logs, you cannot audit network traffic or detect intrusions
resource "aws_flow_log" "main" {
  vpc_id                   = aws_vpc.main.id
  traffic_type             = "ALL"
  log_destination_type     = "cloud-watch-logs"
  log_destination          = aws_cloudwatch_log_group.flow_log.arn
  iam_role_arn             = aws_iam_role.flow_log.arn
  max_aggregation_interval = 60
}

resource "aws_cloudwatch_log_group" "flow_log" {
  name              = "/aws/vpc/flow-logs"
  retention_in_days = 30
}

resource "aws_iam_role" "flow_log" {
  name = "vpc-flow-log-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "vpc-flow-logs.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "flow_log" {
  name = "vpc-flow-log-policy"
  role = aws_iam_role.flow_log.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams"
      ]
      Resource = "*"
    }]
  })
}

# Subnets: NEVER auto-assign public IPs to private subnets
resource "aws_subnet" "private" {
  map_public_ip_on_launch = false  # REQUIRED for private subnets
}
```

### IAM Policies (HIGH)
```hcl
# WRONG - Never do this:
# "Action": "*"
# "Resource": "*"

# CORRECT - Least privilege:
data "aws_iam_policy_document" "example" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject"
    ]
    resources = [
      "${aws_s3_bucket.example.arn}/*"  # Specific resource
    ]
  }
}
```

### CloudWatch/Logging (MEDIUM)
```hcl
# REQUIRED: CloudWatch log groups should have retention
resource "aws_cloudwatch_log_group" "example" {
  name              = "/aws/example"
  retention_in_days = 90  # Don't leave as unlimited

  # RECOMMENDED: Enable encryption
  kms_key_id = aws_kms_key.logs.arn
}
```
"""

GCP_RULES = """
## GCP-Specific Security Rules

### Cloud Storage Buckets
```hcl
resource "google_storage_bucket" "example" {
  name          = "my-bucket"
  location      = "US"
  force_destroy = false  # Prevent accidental deletion

  # REQUIRED: Enable uniform bucket-level access
  uniform_bucket_level_access = true

  # REQUIRED: Enable versioning
  versioning {
    enabled = true
  }

  # RECOMMENDED: Enable logging
  logging {
    log_bucket = google_storage_bucket.logs.name
  }

  # RECOMMENDED: Encryption with CMEK
  encryption {
    default_kms_key_name = google_kms_crypto_key.example.id
  }
}
```

### Compute Instances
```hcl
resource "google_compute_instance" "example" {
  # REQUIRED: Don't use default service account
  service_account {
    email  = google_service_account.custom.email
    scopes = ["cloud-platform"]  # Use specific scopes
  }

  # REQUIRED: Enable shielded VM
  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  # REQUIRED: No public IP for internal instances
  network_interface {
    network    = google_compute_network.vpc.name
    subnetwork = google_compute_subnetwork.private.name
    # Omit access_config for no public IP
  }

  # REQUIRED: Encrypt disks
  boot_disk {
    kms_key_self_link = google_kms_crypto_key.disk.id
  }
}
```

### GKE Clusters
```hcl
resource "google_container_cluster" "example" {
  # REQUIRED: Use private cluster
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = true
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  # REQUIRED: Enable network policy
  network_policy {
    enabled = true
  }

  # REQUIRED: Enable workload identity
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # REQUIRED: Enable binary authorization
  binary_authorization {
    evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
  }
}
```
"""

AZURE_RULES = """
## Azure-Specific Security Rules

### Storage Accounts
```hcl
resource "azurerm_storage_account" "example" {
  name                     = "examplesa"
  resource_group_name      = azurerm_resource_group.example.name
  location                 = azurerm_resource_group.example.location
  account_tier             = "Standard"
  account_replication_type = "GRS"

  # REQUIRED: Enforce HTTPS
  enable_https_traffic_only = true
  min_tls_version           = "TLS1_2"

  # REQUIRED: Disable public access
  public_network_access_enabled = false

  # REQUIRED: Enable encryption
  infrastructure_encryption_enabled = true

  # REQUIRED: Disable blob public access
  allow_nested_items_to_be_public = false

  # RECOMMENDED: Enable soft delete
  blob_properties {
    delete_retention_policy {
      days = 7
    }
    container_delete_retention_policy {
      days = 7
    }
  }
}
```

### Virtual Machines
```hcl
resource "azurerm_linux_virtual_machine" "example" {
  # REQUIRED: Use managed identity instead of passwords
  identity {
    type = "SystemAssigned"
  }

  # REQUIRED: Disable password auth, use SSH
  disable_password_authentication = true

  # REQUIRED: Encrypt disks
  os_disk {
    encryption_at_host_enabled = true
  }
}
```

### AKS Clusters
```hcl
resource "azurerm_kubernetes_cluster" "example" {
  # REQUIRED: Use private cluster
  private_cluster_enabled = true

  # REQUIRED: Enable RBAC
  role_based_access_control_enabled = true

  # REQUIRED: Enable Azure AD integration
  azure_active_directory_role_based_access_control {
    managed            = true
    azure_rbac_enabled = true
  }

  # REQUIRED: Enable network policy
  network_profile {
    network_policy = "azure"  # or "calico"
  }
}
```
"""


def get_security_rules_for_provider(provider: str) -> str:
    """Get security rules for a specific cloud provider.

    Args:
        provider: Cloud provider (aws, gcp, azure)

    Returns:
        String containing security rules to inject into prompt.
    """
    rules = [COMMON_RULES]

    if provider.lower() == "aws":
        rules.append(AWS_RULES)
    elif provider.lower() in ("gcp", "google"):
        rules.append(GCP_RULES)
    elif provider.lower() == "azure":
        rules.append(AZURE_RULES)
    else:
        # Include all if unknown
        rules.extend([AWS_RULES, GCP_RULES, AZURE_RULES])

    return "\n".join(rules)


def load_opa_policies(policies_dir: Optional[Path] = None) -> str:
    """Load OPA/Rego policies from a directory.

    Args:
        policies_dir: Path to directory containing .rego files

    Returns:
        String containing policy content to inject into prompt.
    """
    if not policies_dir:
        # Check common locations
        common_paths = [
            Path("policies"),
            Path("opa"),
            Path(".policies"),
            Path.home() / ".terragen" / "policies",
        ]
        for path in common_paths:
            if path.exists():
                policies_dir = path
                break

    if not policies_dir or not policies_dir.exists():
        return ""

    policies = []
    for rego_file in policies_dir.glob("**/*.rego"):
        try:
            content = rego_file.read_text()
            policies.append(f"### Policy: {rego_file.name}\n```rego\n{content}\n```")
        except Exception:
            continue

    if policies:
        header = """
## Custom OPA Policies
The following custom policies MUST be followed. Violating these will cause the build to fail:

"""
        return header + "\n\n".join(policies)

    return ""


VALIDATION_RULES = """
## CRITICAL: Terraform Validation Requirements

Your code MUST pass `terraform fmt`, `terraform init`, and `terraform validate` on the FIRST attempt.
Follow these rules to prevent validation failures:

### Provider Configuration (REQUIRED)
```hcl
# versions.tf - ALWAYS create this file
terraform {
  required_version = ">= 1.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# providers.tf - ALWAYS create this file
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
```

### Variable Declarations (REQUIRED)
```hcl
# variables.tf - Declare ALL variables used in the code
variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

# ALWAYS provide type and description
# Use default values when sensible
```

### Common Validation Errors to AVOID

1. **Missing required arguments**:
   - Every `aws_security_group` needs `vpc_id`
   - Every `aws_subnet` needs `vpc_id` and `cidr_block`
   - Every `aws_instance` needs `ami` and `instance_type`

2. **Invalid references** (CRITICAL - most common error!):
   - WRONG: `aws_vpc.main.id` (if resource is named differently)
   - CORRECT: Check resource names match exactly
   - **BEFORE referencing ANY resource, VERIFY it is declared in your code**
   - Common missing resources:
     - `aws_iam_role` - MUST be created before Lambda, ECS, EKS reference it
     - `aws_kms_key` - MUST be created before S3, DynamoDB, RDS reference it
     - `aws_security_group` - MUST be created before EC2, RDS, Lambda reference it
     - `aws_subnet` - MUST be created before EC2, RDS, Lambda reference it

3. **Type mismatches**:
   - `count` and `for_each` values must be known at plan time
   - Lists need `[]`, maps need `{}`

4. **Circular dependencies**:
   - Don't reference a resource from within itself
   - Use `depends_on` for implicit dependencies

5. **Deprecated arguments**:
   - AWS Provider 5.x: Use separate resources instead of inline blocks
   - S3: Use `aws_s3_bucket_versioning` not `versioning {}` block
   - S3: Use `aws_s3_bucket_server_side_encryption_configuration` not `server_side_encryption_configuration {}` block

6. **Resource dependency order** (CRITICAL):
   - ALWAYS create supporting resources FIRST:
     1. KMS keys (for encryption)
     2. IAM roles and policies (for permissions)
     3. VPC, subnets, security groups (for networking)
     4. Then main resources (Lambda, RDS, ECS, etc.)
   - If you reference `aws_iam_role.lambda_exec.arn`, you MUST have:
     ```hcl
     resource "aws_iam_role" "lambda_exec" {
       name = "lambda-exec-role"
       assume_role_policy = jsonencode({...})
     }
     ```

### Resource Naming Convention
```hcl
# Use consistent naming: resource "type" "name"
resource "aws_vpc" "main" { }           # Primary VPC
resource "aws_subnet" "private" { }     # Use descriptive names
resource "aws_subnet" "public" { }

# Reference format: aws_vpc.main.id, aws_subnet.private.id
```

### Output Declarations
```hcl
# outputs.tf - Export useful values
output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

# ALWAYS add description to outputs
```
"""


def build_security_prompt_section(
    provider: str, policies_dir: Optional[Path] = None
) -> str:
    """Build the complete security section for the system prompt.

    Args:
        provider: Cloud provider
        policies_dir: Optional path to OPA policies

    Returns:
        Complete security rules section for system prompt.
    """
    sections = []

    # Add validation rules FIRST (most common failure)
    sections.append(VALIDATION_RULES)

    # Add header for security
    sections.append(
        """
## CRITICAL: Security Compliance Requirements

Your generated code MUST pass security scans from tfsec, Checkov, and OPA/Conftest.
Follow these rules to generate compliant code from the start - avoid the fix loop!
"""
    )

    # Add provider-specific rules
    sections.append(get_security_rules_for_provider(provider))

    # Add OPA policies if available
    opa_policies = load_opa_policies(policies_dir)
    if opa_policies:
        sections.append(opa_policies)

    # Add final reminder - compact checklist
    sections.append(
        """
## QUICK CHECKLIST (mandatory)
**Validation**: versions.tf + providers.tf + variables.tf (all vars declared with type/description)
**References**: Every resource you reference MUST be declared first (IAM roles, KMS keys, subnets)
**S3**: encryption + versioning + public_access_block + logging
**Security Groups**: description + NO 0.0.0.0/0 on ports 22/3389/DB
**RDS**: storage_encrypted=true, publicly_accessible=false, backup_retention>0
**VPC**: aws_flow_log REQUIRED, private subnets map_public_ip_on_launch=false
**EKS**: secrets encryption + control plane logging + private endpoint
**IAM**: NO wildcard (*) actions/resources
**Tags**: Environment + ManagedBy on all resources

Generate secure code FIRST TIME - the fix loop is expensive!
"""
    )

    return "\n".join(sections)
