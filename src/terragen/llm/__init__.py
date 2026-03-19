"""
TerraGen LLM - Unified LLM client with intelligent routing and fallback support.
"""

from .base import (
    ContentBlock,
    LLMResponse,
    StopReason,
    TextBlock,
    ToolCall,
    Usage,
)
from .exceptions import (
    APIError,
    AuthenticationError,
    LLMError,
    NoAvailableProviderError,
    RateLimitError,
    TimeoutError,
)
from .client import UnifiedLLMClient
from .model_router import (
    ModelRouter,
    ModelConfig,
    ComplexityTier,
    ClassificationResult,
    estimate_cost_savings,
)

__all__ = [
    # Client
    "UnifiedLLMClient",
    # Router
    "ModelRouter",
    "ModelConfig",
    "ComplexityTier",
    "ClassificationResult",
    "estimate_cost_savings",
    # Base types
    "ContentBlock",
    "LLMResponse",
    "StopReason",
    "TextBlock",
    "ToolCall",
    "Usage",
    # Exceptions
    "APIError",
    "AuthenticationError",
    "LLMError",
    "NoAvailableProviderError",
    "RateLimitError",
    "TimeoutError",
]
