"""
Intelligent Model Router - Selects optimal model based on task complexity.

Analyzes the user prompt to determine complexity and routes to the
most cost-effective model that can handle the task.

Tiers:
- Simple (0-30): GPT-4o-mini, Grok-4.1-fast → Fast, cheap, good for basic resources
- Medium (31-70): GPT-4o, Grok-4-fast → Balanced quality and cost
- Complex (71-100): Claude Sonnet, Grok-4.1 → Best quality for complex infra

Includes automatic fallback: if a model fails validation/security,
escalates to the next tier.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ComplexityTier(Enum):
    """Complexity tiers for model selection."""
    SIMPLE = "simple"      # Score 0-30
    MEDIUM = "medium"      # Score 31-70
    COMPLEX = "complex"    # Score 71-100


@dataclass
class ModelConfig:
    """Configuration for a model."""
    provider: str
    model: str
    tier: ComplexityTier
    cost_per_1m_input: float
    cost_per_1m_output: float


@dataclass
class ClassificationResult:
    """Result of prompt classification."""
    score: int  # 0-100
    tier: ComplexityTier
    reasons: list[str]
    detected_resources: list[str]
    detected_features: list[str]


# Model configurations by tier
# Updated with latest Grok 4.1 models (Jan 2026)
MODEL_TIERS: dict[ComplexityTier, list[ModelConfig]] = {
    ComplexityTier.SIMPLE: [
        # Grok 4.1 Fast - best for tool calling, very cheap ($0.20/1M input)
        ModelConfig("xai", "grok-4-1-fast", ComplexityTier.SIMPLE, 0.20, 0.50),
        ModelConfig("openai", "gpt-4o-mini", ComplexityTier.SIMPLE, 0.15, 0.60),
        ModelConfig("deepseek", "deepseek-chat", ComplexityTier.SIMPLE, 0.14, 0.28),
    ],
    ComplexityTier.MEDIUM: [
        # Grok 4 Fast - good balance of speed and quality
        ModelConfig("xai", "grok-4-fast", ComplexityTier.MEDIUM, 1.0, 4.0),
        ModelConfig("openai", "gpt-4o", ComplexityTier.MEDIUM, 2.50, 10.0),
    ],
    ComplexityTier.COMPLEX: [
        ModelConfig("anthropic", "claude-sonnet-4-20250514", ComplexityTier.COMPLEX, 3.0, 15.0),
        # Grok 4.1 - most intelligent, #1 on LMArena
        ModelConfig("xai", "grok-4-1", ComplexityTier.COMPLEX, 3.0, 15.0),
        ModelConfig("openai", "gpt-4o", ComplexityTier.COMPLEX, 2.50, 10.0),
    ],
}

# Escalation path: Simple → Medium → Complex
ESCALATION_PATH = [ComplexityTier.SIMPLE, ComplexityTier.MEDIUM, ComplexityTier.COMPLEX]


# === Classification Rules ===

# High complexity resources (score +15-25 each)
COMPLEX_RESOURCES = {
    # Kubernetes
    r"\b(eks|gke|aks|kubernetes|k8s)\b": 25,
    r"\b(helm|istio|service\s*mesh)\b": 20,

    # Databases - managed
    r"\b(rds|aurora|documentdb|dynamodb|cloud\s*sql|cosmos\s*db)\b": 15,
    r"\b(elasticache|redis|memcached)\b": 12,

    # Networking - complex
    r"\b(transit\s*gateway|direct\s*connect|vpn|peering)\b": 20,
    r"\b(load\s*balancer|alb|nlb|elb)\b": 10,
    r"\b(cloudfront|cdn|waf)\b": 12,

    # Serverless - complex patterns
    r"\b(step\s*functions?|eventbridge|sqs|sns|kinesis)\b": 15,
    r"\b(api\s*gateway|apigw)\b": 12,

    # Security/Identity
    r"\b(cognito|auth0|identity|iam\s*role|service\s*account)\b": 10,
    r"\b(secrets?\s*manager|parameter\s*store|kms)\b": 10,

    # CI/CD
    r"\b(codepipeline|codebuild|github\s*actions?)\b": 12,

    # Multi-region/HA
    r"\b(multi[_-]?(az|region)|disaster\s*recovery|dr)\b": 20,
    r"\b(global|cross[_-]?region|replication)\b": 15,
}

# Medium complexity resources (score +5-10 each)
MEDIUM_RESOURCES = {
    r"\b(lambda|function|serverless)\b": 8,
    r"\b(ec2|instance|vm|compute)\b": 6,
    r"\b(vpc|network|subnet)\b": 5,
    r"\b(security\s*group|firewall|nsg)\b": 5,
    r"\b(route\s*53|dns|domain)\b": 6,
    r"\b(cloudwatch|monitoring|logging)\b": 5,
    r"\b(ecs|fargate|container)\b": 10,
    r"\b(ecr|gcr|acr|registry)\b": 5,
}

# Simple resources (score +2-4 each)
SIMPLE_RESOURCES = {
    r"\b(s3|bucket|storage|blob)\b": 3,
    r"\b(iam\s*user|iam\s*policy)\b": 4,
    r"\b(sns\s*topic|sqs\s*queue)\b": 3,
    r"\b(cloudwatch\s*alarm)\b": 3,
}

# Complexity modifiers
COMPLEXITY_MODIFIERS = {
    # Production/HA requirements
    r"\b(production|prod)\b": 15,
    r"\b(high\s*availability|ha|redundant)\b": 15,
    r"\b(auto[_-]?scaling|scale)\b": 10,

    # Security requirements
    r"\b(complian(ce|t)|hipaa|pci|sox|gdpr)\b": 20,
    r"\b(encrypt(ion|ed)?|secure|hardened)\b": 5,

    # Environment complexity
    r"\b(multi[_-]?tenant|saas)\b": 15,
    r"\b(microservice|distributed)\b": 12,

    # Simplicity indicators (negative)
    r"\b(simple|basic|minimal|demo|test|dev)\b": -10,
    r"\b(single|one|just)\b": -5,
}


class ModelRouter:
    """Intelligent model router that selects optimal model based on task complexity."""

    def __init__(
        self,
        available_providers: Optional[list[str]] = None,
        force_tier: Optional[ComplexityTier] = None,
    ):
        """Initialize the model router.

        Args:
            available_providers: List of providers with API keys configured.
            force_tier: Force a specific tier (for testing/override).
        """
        self.available_providers = available_providers or []
        self.force_tier = force_tier
        self._fallback_count = 0

    def classify_prompt(self, prompt: str) -> ClassificationResult:
        """Classify a prompt to determine its complexity.

        Args:
            prompt: The user's infrastructure request.

        Returns:
            ClassificationResult with score, tier, and analysis.
        """
        prompt_lower = prompt.lower()
        score = 0
        reasons = []
        detected_resources = []
        detected_features = []

        # Check complex resources
        for pattern, points in COMPLEX_RESOURCES.items():
            if re.search(pattern, prompt_lower):
                score += points
                match = re.search(pattern, prompt_lower)
                if match:
                    detected_resources.append(match.group())
                    reasons.append(f"+{points}: Complex resource '{match.group()}'")

        # Check medium resources
        for pattern, points in MEDIUM_RESOURCES.items():
            if re.search(pattern, prompt_lower):
                score += points
                match = re.search(pattern, prompt_lower)
                if match:
                    detected_resources.append(match.group())
                    reasons.append(f"+{points}: Medium resource '{match.group()}'")

        # Check simple resources
        for pattern, points in SIMPLE_RESOURCES.items():
            if re.search(pattern, prompt_lower):
                score += points
                match = re.search(pattern, prompt_lower)
                if match:
                    detected_resources.append(match.group())
                    reasons.append(f"+{points}: Simple resource '{match.group()}'")

        # Apply modifiers
        for pattern, points in COMPLEXITY_MODIFIERS.items():
            if re.search(pattern, prompt_lower):
                score += points
                match = re.search(pattern, prompt_lower)
                if match:
                    detected_features.append(match.group())
                    sign = "+" if points > 0 else ""
                    reasons.append(f"{sign}{points}: Modifier '{match.group()}'")

        # Count number of distinct resources mentioned (more = more complex)
        resource_count = len(set(detected_resources))
        if resource_count > 5:
            bonus = min((resource_count - 5) * 3, 15)
            score += bonus
            reasons.append(f"+{bonus}: {resource_count} distinct resources")

        # Clamp score to 0-100
        score = max(0, min(100, score))

        # Determine tier
        if score <= 30:
            tier = ComplexityTier.SIMPLE
        elif score <= 70:
            tier = ComplexityTier.MEDIUM
        else:
            tier = ComplexityTier.COMPLEX

        return ClassificationResult(
            score=score,
            tier=tier,
            reasons=reasons,
            detected_resources=list(set(detected_resources)),
            detected_features=list(set(detected_features)),
        )

    def select_model(
        self,
        prompt: str,
        escalate_from: Optional[ComplexityTier] = None,
    ) -> tuple[ModelConfig, ClassificationResult]:
        """Select the optimal model for a prompt.

        Args:
            prompt: The user's infrastructure request.
            escalate_from: If set, escalate from this tier (after failure).

        Returns:
            Tuple of (ModelConfig, ClassificationResult).
        """
        classification = self.classify_prompt(prompt)

        # Use forced tier if set
        if self.force_tier:
            tier = self.force_tier
        elif escalate_from:
            # Escalate to next tier
            current_idx = ESCALATION_PATH.index(escalate_from)
            next_idx = min(current_idx + 1, len(ESCALATION_PATH) - 1)
            tier = ESCALATION_PATH[next_idx]
            self._fallback_count += 1
        else:
            tier = classification.tier

        # Get available models for this tier
        models = MODEL_TIERS[tier]

        # Filter by available providers
        if self.available_providers:
            available_models = [
                m for m in models
                if m.provider in self.available_providers
            ]
            if available_models:
                models = available_models

        # Return first available model
        if models:
            return models[0], classification

        # Fallback: try next tier
        if tier != ComplexityTier.COMPLEX:
            return self.select_model(prompt, escalate_from=tier)

        # Ultimate fallback: first model from complex tier
        return MODEL_TIERS[ComplexityTier.COMPLEX][0], classification

    def get_fallback_model(
        self,
        current_model: ModelConfig,
        prompt: str,
    ) -> Optional[ModelConfig]:
        """Get a fallback model after failure.

        Args:
            current_model: The model that failed.
            prompt: The original prompt.

        Returns:
            Next model to try, or None if no fallback available.
        """
        current_tier = current_model.tier
        current_idx = ESCALATION_PATH.index(current_tier)

        # Try next tier
        if current_idx < len(ESCALATION_PATH) - 1:
            next_tier = ESCALATION_PATH[current_idx + 1]
            models = MODEL_TIERS[next_tier]

            # Filter by available providers
            if self.available_providers:
                available_models = [
                    m for m in models
                    if m.provider in self.available_providers
                ]
                if available_models:
                    models = available_models

            if models:
                self._fallback_count += 1
                return models[0]

        return None

    def get_stats(self) -> dict:
        """Get routing statistics."""
        return {
            "fallback_count": self._fallback_count,
        }


def estimate_cost_savings(
    prompt: str,
    router: Optional[ModelRouter] = None,
) -> dict:
    """Estimate cost savings from intelligent routing.

    Args:
        prompt: The user's infrastructure request.
        router: Optional router instance.

    Returns:
        Dictionary with cost comparison.
    """
    if router is None:
        router = ModelRouter()

    model, classification = router.select_model(prompt)

    # Estimate tokens (rough)
    estimated_input_tokens = 50000  # ~50K input tokens typical
    estimated_output_tokens = 10000  # ~10K output tokens typical

    # Calculate costs
    selected_cost = (
        model.cost_per_1m_input * estimated_input_tokens / 1_000_000 +
        model.cost_per_1m_output * estimated_output_tokens / 1_000_000
    )

    # Compare to always using Claude Sonnet
    sonnet = MODEL_TIERS[ComplexityTier.COMPLEX][0]
    sonnet_cost = (
        sonnet.cost_per_1m_input * estimated_input_tokens / 1_000_000 +
        sonnet.cost_per_1m_output * estimated_output_tokens / 1_000_000
    )

    savings = sonnet_cost - selected_cost
    savings_pct = (savings / sonnet_cost * 100) if sonnet_cost > 0 else 0

    return {
        "selected_model": f"{model.provider}/{model.model}",
        "selected_tier": classification.tier.value,
        "complexity_score": classification.score,
        "estimated_cost": f"${selected_cost:.2f}",
        "sonnet_cost": f"${sonnet_cost:.2f}",
        "savings": f"${savings:.2f}",
        "savings_percent": f"{savings_pct:.0f}%",
        "reasons": classification.reasons[:5],  # Top 5 reasons
    }
