"""
TerraGen Questions - Interactive clarification prompts.
"""

import json

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from .config import get_region_examples, LLM_MODELS, FALLBACK_ORDER
from .llm import UnifiedLLMClient

console = Console()


def generate_clarifying_questions_llm(prompt: str, provider: str = "aws") -> list:
    """Generate clarifying questions using the LLM based on the user's prompt.

    Returns a list of questions with format:
    [{"id": "...", "question": "...", "options": [...], "default": "..."}]
    """
    client = UnifiedLLMClient(
        fallback_order=FALLBACK_ORDER,
        models=LLM_MODELS,
    )

    system_prompt = """You are an expert infrastructure architect helping users define their Terraform requirements.

Given a user's infrastructure request, generate 2-4 clarifying questions that would help you generate better Terraform code.

Focus on questions about:
- Environment (production/staging/dev) and availability requirements
- Specific configurations (sizes, counts, versions)
- Security requirements (encryption, access controls)
- Networking requirements (VPC, subnets, public/private)
- Cost considerations (instance types, reserved capacity)

Return your response as a JSON array with this exact format:
[
  {
    "id": "unique_id",
    "question": "The question text",
    "options": ["option1", "option2", "option3"],
    "default": "option1"
  }
]

Only return the JSON array, no other text."""

    user_prompt = f"""Cloud Provider: {provider}
User Request: {prompt}

Generate clarifying questions that would help you create better Terraform code for this request."""

    try:
        response = client.create_message(
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        response_text = response.get_text().strip()

        # Handle potential markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]

        questions = json.loads(response_text)
        return questions

    except Exception as e:
        console.print(f"[yellow]Warning: Could not generate LLM questions: {e}[/yellow]")
        # Fallback to basic questions
        return [
            {
                "id": "environment",
                "question": "What environment is this for?",
                "options": ["production", "staging", "development"],
                "default": "development",
            }
        ]


# Service type detection patterns
SERVICE_PATTERNS = {
    "database": ["database", "rds", "db", "postgres", "mysql", "sql", "aurora", "dynamodb"],
    "kubernetes": ["kubernetes", "eks", "gke", "aks", "k8s", "cluster"],
    "storage": ["s3", "bucket", "storage", "blob", "gcs"],
    "serverless": ["lambda", "function", "serverless", "api gateway"],
    "compute": ["ec2", "vm", "instance", "compute"],
    "networking": ["vpc", "network", "subnet", "load balancer", "cdn"],
    "ml": ["sagemaker", "ml", "machine learning", "ai", "vertex"],
}


def detect_service_type(prompt: str) -> str:
    """Detect the primary service type from a prompt."""
    prompt_lower = prompt.lower()
    for service_type, patterns in SERVICE_PATTERNS.items():
        if any(pattern in prompt_lower for pattern in patterns):
            return service_type
    return "general"


def get_questions_for_service(service_type: str, provider: str = "aws") -> list:
    """Get relevant questions for a service type."""
    questions = [
        {
            "id": "environment",
            "question": "What environment is this for?",
            "options": ["production", "staging", "development"],
            "default": "development",
        },
    ]

    if service_type == "database":
        questions.extend([
            {
                "id": "db_engine",
                "question": "Which database engine?",
                "options": ["postgresql", "mysql", "aurora"] if provider == "aws" else ["postgresql", "mysql"],
                "default": "postgresql",
            },
            {
                "id": "db_multi_az",
                "question": "Enable high availability (Multi-AZ)?",
                "options": ["yes", "no"],
                "default": "no",
            },
        ])

    elif service_type == "kubernetes":
        questions.extend([
            {
                "id": "k8s_node_count",
                "question": "Number of worker nodes?",
                "options": ["2", "3", "5", "10"],
                "default": "3",
            },
            {
                "id": "k8s_autoscaling",
                "question": "Enable cluster autoscaling?",
                "options": ["yes", "no"],
                "default": "yes",
            },
        ])

    elif service_type == "storage":
        questions.extend([
            {
                "id": "storage_versioning",
                "question": "Enable versioning?",
                "options": ["yes", "no"],
                "default": "yes",
            },
            {
                "id": "storage_encryption",
                "question": "Enable encryption?",
                "options": ["yes", "no"],
                "default": "yes",
            },
        ])

    elif service_type == "serverless":
        questions.extend([
            {
                "id": "lambda_memory",
                "question": "Function memory (MB)?",
                "options": ["128", "256", "512", "1024"],
                "default": "256",
            },
        ])

    return questions


def ask_clarifying_questions(prompt: str) -> dict:
    """Ask user clarifying questions about their infrastructure requirements."""
    console.print(Panel.fit(
        "[bold blue]Let me ask a few questions to generate better Terraform code[/bold blue]",
        title="Clarification"
    ))

    answers = {}
    prompt_lower = prompt.lower()

    # Cloud provider
    console.print("\n[bold]1. Cloud Provider[/bold]")
    options = ["AWS", "GCP", "Azure", "Multi-cloud"]
    for i, opt in enumerate(options, 1):
        console.print(f"   {i}. {opt}")
    choice = Prompt.ask("Select", choices=["1", "2", "3", "4"], default="1")
    provider_map = {"1": "aws", "2": "gcp", "3": "azure", "4": "multi"}
    answers["provider"] = provider_map[choice]

    # Environment
    console.print("\n[bold]2. Environment[/bold]")
    options = ["Production (HA, multi-AZ)", "Staging", "Development (cost-optimized)"]
    for i, opt in enumerate(options, 1):
        console.print(f"   {i}. {opt}")
    choice = Prompt.ask("Select", choices=["1", "2", "3"], default="3")
    env_map = {"1": "production", "2": "staging", "3": "development"}
    answers["environment"] = env_map[choice]
    is_prod = answers["environment"] == "production"

    # Region based on provider
    console.print("\n[bold]3. Region[/bold]")
    regions = get_region_examples(answers["provider"])

    for i, opt in enumerate(regions, 1):
        console.print(f"   {i}. {opt}")
    console.print(f"   5. Other")
    choice = Prompt.ask("Select", choices=["1", "2", "3", "4", "5"], default="1")
    if choice == "5":
        answers["region"] = Prompt.ask("Enter region")
    else:
        answers["region"] = regions[int(choice) - 1]

    # Service-specific questions based on prompt content
    question_num = 4

    if any(s in prompt_lower for s in ["database", "rds", "db", "postgres", "mysql", "sql"]):
        console.print(f"\n[bold]{question_num}. Database Configuration[/bold]")
        answers["db_multi_az"] = Confirm.ask("Enable Multi-AZ/HA?", default=is_prod)
        answers["db_engine"] = Prompt.ask("Database engine", choices=["postgresql", "mysql", "aurora"], default="postgresql")
        question_num += 1

    if any(s in prompt_lower for s in ["kubernetes", "eks", "gke", "aks", "k8s"]):
        console.print(f"\n[bold]{question_num}. Kubernetes Configuration[/bold]")
        answers["k8s_node_count"] = Prompt.ask("Number of nodes", default="3" if is_prod else "2")
        answers["k8s_autoscaling"] = Confirm.ask("Enable autoscaling?", default=is_prod)
        question_num += 1

    if any(s in prompt_lower for s in ["s3", "bucket", "storage"]):
        console.print(f"\n[bold]{question_num}. Storage Configuration[/bold]")
        answers["storage_versioning"] = Confirm.ask("Enable versioning?", default=is_prod)
        answers["storage_encryption"] = Confirm.ask("Enable encryption?", default=True)
        question_num += 1

    if any(s in prompt_lower for s in ["lambda", "function", "serverless"]):
        console.print(f"\n[bold]{question_num}. Serverless Configuration[/bold]")
        answers["lambda_memory"] = Prompt.ask("Memory (MB)", choices=["128", "256", "512", "1024"], default="256")
        question_num += 1

    if is_prod:
        console.print(f"\n[bold]{question_num}. Production Settings[/bold]")
        answers["enable_backups"] = Confirm.ask("Enable automated backups?", default=True)
        answers["enable_monitoring"] = Confirm.ask("Enable monitoring?", default=True)

    return answers


def ask_backend_config(backend: str, provider: str, region: str) -> dict:
    """Ask for backend configuration parameters."""
    console.print(Panel.fit(
        f"[bold blue]Configure {backend.upper()} Backend[/bold blue]\n"
        f"[dim]Press Enter to use defaults[/dim]",
        title="State Backend"
    ))

    config = {"type": backend}

    if backend == "s3":
        config["bucket"] = Prompt.ask(
            "S3 bucket name",
            default=f"terraform-state-{region}"
        )
        config["key"] = Prompt.ask(
            "State file key",
            default="terraform.tfstate"
        )
        config["region"] = Prompt.ask(
            "S3 bucket region",
            default=region
        )
        config["dynamodb_table"] = Prompt.ask(
            "DynamoDB table for locking",
            default="terraform-locks"
        )
        config["encrypt"] = Confirm.ask("Encrypt state file?", default=True)

    elif backend == "gcs":
        config["bucket"] = Prompt.ask(
            "GCS bucket name",
            default=f"terraform-state-{region}"
        )
        config["prefix"] = Prompt.ask(
            "State file prefix",
            default="terraform/state"
        )

    elif backend == "azurerm":
        config["resource_group_name"] = Prompt.ask(
            "Resource group name",
            default="terraform-state-rg"
        )
        config["storage_account_name"] = Prompt.ask(
            "Storage account name",
            default="tfstate"
        )
        config["container_name"] = Prompt.ask(
            "Container name",
            default="tfstate"
        )
        config["key"] = Prompt.ask(
            "State file key",
            default="terraform.tfstate"
        )

    elif backend == "remote":  # Terraform Cloud
        config["organization"] = Prompt.ask(
            "Terraform Cloud organization",
            default=""
        )
        config["workspace"] = Prompt.ask(
            "Workspace name",
            default="default"
        )

    return config


def build_backend_context(backend_config: dict) -> str:
    """Build backend configuration context for the prompt.

    When user selects a backend type but doesn't provide specific values,
    generate a COMMENTED backend block with TODO placeholders that the user
    must fill in before running terraform init.
    """
    if not backend_config:
        return ""

    backend_type = backend_config.get("type", "")

    # Check if specific config values were provided
    has_specific_config = any(
        k != "type" and v is not None
        for k, v in backend_config.items()
    )

    if has_specific_config:
        # User provided specific values - generate active backend
        return _build_active_backend(backend_config)
    else:
        # Only type selected - generate commented backend with TODOs
        return _build_commented_backend(backend_type)


def _build_active_backend(backend_config: dict) -> str:
    """Build active backend configuration with user-provided values."""
    backend_type = backend_config.get("type", "")
    context = [f"\n## State Backend Configuration\nGenerate an ACTIVE (uncommented) {backend_type} backend block with these values:"]

    if backend_type == "s3":
        # Build S3 backend block
        s3_lines = ['    bucket         = "{}"'.format(backend_config.get('bucket', 'MISSING-BUCKET-NAME'))]
        s3_lines.append('    key            = "{}"'.format(backend_config.get('key', 'terraform.tfstate')))
        s3_lines.append('    region         = "{}"'.format(backend_config.get('region', 'us-east-1')))
        s3_lines.append('    encrypt        = true')
        if backend_config.get('dynamodb_table'):
            s3_lines.append('    dynamodb_table = "{}"'.format(backend_config['dynamodb_table']))

        context.append(f"""
```hcl
terraform {{
  backend "s3" {{
{chr(10).join(s3_lines)}
  }}
}}
```

IMPORTANT:
- Generate this EXACT backend block (uncommented) in backend.tf
- The S3 bucket "{backend_config.get('bucket', 'MISSING')}" MUST exist before running terraform init
{"- The DynamoDB table for locking MUST exist" if backend_config.get('dynamodb_table') else ""}
- If initialization fails with "bucket not found", the user needs to create the bucket first""")

    elif backend_type == "gcs":
        context.append(f"""
```hcl
terraform {{
  backend "gcs" {{
    bucket = "{backend_config.get('bucket', 'MISSING-BUCKET-NAME')}"
    prefix = "{backend_config.get('prefix', 'terraform/state')}"
  }}
}}
```

IMPORTANT:
- Generate this EXACT backend block (uncommented) in backend.tf
- The GCS bucket "{backend_config.get('bucket', 'MISSING')}" MUST exist before running terraform init""")

    elif backend_type == "azurerm":
        context.append(f"""
```hcl
terraform {{
  backend "azurerm" {{
    resource_group_name  = "{backend_config.get('resource_group_name', 'MISSING-RG')}"
    storage_account_name = "{backend_config.get('storage_account_name', 'MISSING-STORAGE')}"
    container_name       = "{backend_config.get('container_name', 'tfstate')}"
    key                  = "{backend_config.get('key', 'terraform.tfstate')}"
  }}
}}
```

IMPORTANT:
- Generate this EXACT backend block (uncommented) in backend.tf
- The Azure storage account and container MUST exist before running terraform init""")

    elif backend_type == "remote":
        context.append(f"""
```hcl
terraform {{
  cloud {{
    organization = "{backend_config.get('organization', 'MISSING-ORG')}"
    workspaces {{
      name = "{backend_config.get('workspace', 'MISSING-WORKSPACE')}"
    }}
  }}
}}
```

IMPORTANT:
- Generate this EXACT backend block (uncommented) in backend.tf
- The Terraform Cloud organization and workspace MUST exist before running terraform init""")

    return "\n".join(context)


def _build_commented_backend(backend_type: str) -> str:
    """Build commented backend configuration when only type is selected.

    The user must fill in the TODO values and uncomment before using.
    """
    context = [f"""
## State Backend Configuration
The user selected {backend_type.upper()} backend. Generate backend.tf with:
1. ONLY the {backend_type} backend block (not other backends)
2. The backend block should be COMMENTED OUT with TODO placeholders
3. Clear instructions for the user to fill in values

Example for backend.tf:"""]

    if backend_type == "s3":
        context.append("""
```hcl
# S3 Backend Configuration
# ========================
# Before using this backend:
# 1. Create an S3 bucket for state storage
# 2. Create a DynamoDB table for state locking (optional but recommended)
# 3. Fill in the values below and uncomment the terraform block
#
# terraform {
#   backend "s3" {
#     bucket         = "TODO-your-state-bucket-name"    # S3 bucket name
#     key            = "terraform.tfstate"              # State file path in bucket
#     region         = "us-east-1"                      # AWS region
#     encrypt        = true                             # Enable encryption
#     dynamodb_table = "TODO-your-lock-table"           # DynamoDB table for locking
#   }
# }
```""")
    elif backend_type == "gcs":
        context.append("""
```hcl
# GCS Backend Configuration
# =========================
# Before using this backend:
# 1. Create a GCS bucket for state storage
# 2. Fill in the values below and uncomment the terraform block
#
# terraform {
#   backend "gcs" {
#     bucket = "TODO-your-state-bucket-name"    # GCS bucket name
#     prefix = "terraform/state"                # State file prefix
#   }
# }
```""")
    elif backend_type == "azurerm":
        context.append("""
```hcl
# Azure Storage Backend Configuration
# ====================================
# Before using this backend:
# 1. Create a resource group, storage account, and container
# 2. Fill in the values below and uncomment the terraform block
#
# terraform {
#   backend "azurerm" {
#     resource_group_name  = "TODO-your-rg-name"         # Resource group
#     storage_account_name = "TODO-your-storage-account" # Storage account
#     container_name       = "tfstate"                   # Container name
#     key                  = "terraform.tfstate"         # State file name
#   }
# }
```""")
    elif backend_type in ("remote", "terraform_cloud"):
        context.append("""
```hcl
# Terraform Cloud Backend Configuration
# ======================================
# Before using this backend:
# 1. Create a Terraform Cloud account and organization
# 2. Create a workspace
# 3. Fill in the values below and uncomment the terraform block
#
# terraform {
#   cloud {
#     organization = "TODO-your-organization"
#     workspaces {
#       name = "TODO-your-workspace"
#     }
#   }
# }
```""")

    context.append("""
IMPORTANT: Generate ONLY this backend type in backend.tf, NOT other backend examples.
The backend block MUST be commented out with TODO placeholders as shown above.""")

    return "\n".join(context)


def build_clarification_context(clarifications: dict) -> str:
    """Build context string from clarification answers."""
    if not clarifications:
        return ""

    context = []
    env = clarifications.get("environment", "development")
    context.append(f"- Environment: {env}")

    if clarifications.get("db_multi_az"):
        context.append("- Database: Multi-AZ/HA enabled")
    if clarifications.get("db_engine"):
        context.append(f"- Database Engine: {clarifications['db_engine']}")
    if clarifications.get("k8s_node_count"):
        context.append(f"- Kubernetes Nodes: {clarifications['k8s_node_count']}")
    if clarifications.get("k8s_autoscaling"):
        context.append("- Kubernetes Autoscaling: Enabled")
    if clarifications.get("storage_versioning"):
        context.append("- Storage Versioning: Enabled")
    if clarifications.get("storage_encryption"):
        context.append("- Storage Encryption: Enabled")
    if clarifications.get("lambda_memory"):
        context.append(f"- Lambda Memory: {clarifications['lambda_memory']}MB")
    if clarifications.get("enable_backups"):
        context.append("- Automated Backups: Enabled")
    if clarifications.get("enable_monitoring"):
        context.append("- Monitoring: Enabled")

    # Handle backend configuration
    backend = clarifications.get("backend")
    if backend and backend != "local":
        backend_descriptions = {
            "s3": "AWS S3 with DynamoDB for locking",
            "gcs": "Google Cloud Storage",
            "azurerm": "Azure Blob Storage",
            "remote": "Terraform Cloud/Enterprise",
        }
        context.append(f"- State Backend: {backend_descriptions.get(backend, backend)}")
        if clarifications.get("backend_instruction"):
            context.append(f"- {clarifications['backend_instruction']}")

    # Handle production options from InfraBuilder
    if clarifications.get("high-availability"):
        context.append("- High Availability: Enabled (multi-AZ, redundancy)")
    if clarifications.get("encryption"):
        context.append("- Encryption: Enabled (at rest and in transit)")
    if clarifications.get("auto-scaling"):
        context.append("- Auto-scaling: Enabled")
    if clarifications.get("monitoring"):
        context.append("- Monitoring: Enabled (CloudWatch/Stackdriver/Azure Monitor)")
    if clarifications.get("backup"):
        context.append("- Automated Backups: Enabled")
    if clarifications.get("disaster-recovery"):
        context.append("- Disaster Recovery: Enabled (cross-region replication)")
    if clarifications.get("cost-optimization"):
        context.append("- Cost Optimization: Apply reserved capacity, spot instances where appropriate")
    if clarifications.get("compliance"):
        context.append("- Compliance: Enable audit logging, encryption, access controls")

    return "\n".join(context)
