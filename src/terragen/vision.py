"""
Vision module for analyzing architecture diagrams using Claude.
"""

import base64
import re
from pathlib import Path
from typing import Optional

import anthropic

VISION_SYSTEM_PROMPT = """You are an expert cloud architect and Terraform engineer.
Your task is to analyze architecture diagrams and generate production-ready Terraform code.

When analyzing a diagram:
1. Identify all cloud resources (compute, storage, databases, networking, etc.)
2. Understand the connections and data flow between components
3. Determine the cloud provider (AWS, GCP, Azure) from the icons/labels
4. Note any specifications mentioned (instance types, sizes, etc.)

Generate a detailed description of the infrastructure that can be used to create Terraform code."""

DIAGRAM_ANALYSIS_PROMPT = """Analyze this architecture diagram and describe the infrastructure in detail.

For each component, identify:
- Resource type (EC2, RDS, S3, Lambda, VPC, etc.)
- Specifications if visible (instance type, size, etc.)
- Connections to other components
- Security groups and networking requirements
- Any labels or names shown

Output a structured description that can be used to generate Terraform code.

Format your response as:

## Cloud Provider
[AWS/GCP/Azure - based on the icons or labels in the diagram]

## Components
[List each component with details]

## Networking
[VPCs, subnets, security groups, load balancers]

## Data Flow
[How components connect and communicate]

## Additional Requirements
[Any other infrastructure needs visible in the diagram]

{additional_context}"""


def analyze_diagram(
    image_data: str,
    additional_context: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict:
    """
    Analyze an architecture diagram using Claude's vision capabilities.

    Args:
        image_data: Base64 encoded image data (with or without data URI prefix)
        additional_context: Optional additional context from the user
        api_key: Optional Anthropic API key (uses env var if not provided)

    Returns:
        dict with 'analysis' (text description) and 'prompt' (for code generation)
    """
    client = anthropic.Anthropic(api_key=api_key)

    # Handle base64 data URI format
    if image_data.startswith("data:"):
        # Extract media type and base64 data
        match = re.match(r"data:(image/\w+);base64,(.+)", image_data)
        if match:
            media_type = match.group(1)
            base64_data = match.group(2)
        else:
            raise ValueError("Invalid image data format")
    else:
        # Assume raw base64, default to PNG
        media_type = "image/png"
        base64_data = image_data

    # Build the prompt
    context_section = ""
    if additional_context:
        context_section = f"\n\nUser's additional context:\n{additional_context}"

    prompt = DIAGRAM_ANALYSIS_PROMPT.format(additional_context=context_section)

    # Call Claude with vision
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=VISION_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )

    analysis = response.content[0].text

    # Build a prompt for Terraform generation
    terraform_prompt = build_terraform_prompt(analysis, additional_context)

    return {
        "analysis": analysis,
        "prompt": terraform_prompt,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }


def build_terraform_prompt(analysis: str, additional_context: Optional[str] = None) -> str:
    """
    Build a detailed prompt for Terraform code generation from diagram analysis.

    Args:
        analysis: The analysis text from Claude vision
        additional_context: Optional user-provided context

    Returns:
        A prompt string for Terraform generation
    """
    prompt = f"""Generate production-ready Terraform code based on this architecture analysis:

{analysis}

Requirements:
- Create all resources identified in the analysis
- Set up proper networking (VPC, subnets, security groups)
- Configure IAM roles and policies with least privilege
- Enable encryption at rest for all storage
- Add appropriate tags for resource management
- Include variables for configurable values
- Add outputs for important resource attributes
"""

    if additional_context:
        prompt += f"\nAdditional requirements from user:\n{additional_context}\n"

    return prompt


def analyze_diagram_from_file(
    file_path: str | Path,
    additional_context: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict:
    """
    Analyze an architecture diagram from a file path.

    Args:
        file_path: Path to the image file
        additional_context: Optional additional context
        api_key: Optional Anthropic API key

    Returns:
        dict with analysis results
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"Image file not found: {file_path}")

    # Determine media type from extension
    ext_to_media = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }

    ext = file_path.suffix.lower()
    if ext not in ext_to_media:
        raise ValueError(f"Unsupported image format: {ext}")

    media_type = ext_to_media[ext]

    # Read and encode the file
    with open(file_path, "rb") as f:
        base64_data = base64.b64encode(f.read()).decode("utf-8")

    image_data = f"data:{media_type};base64,{base64_data}"

    return analyze_diagram(image_data, additional_context, api_key)
