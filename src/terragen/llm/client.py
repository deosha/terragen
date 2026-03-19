"""
Unified LLM client with fallback support and intelligent routing.
"""

import os
from typing import Any, Optional

from .base import LLMResponse
from .exceptions import (
    APIError,
    AuthenticationError,
    NoAvailableProviderError,
    RateLimitError,
    TimeoutError,
)
from .anthropic_adapter import AnthropicAdapter
from .openai_adapter import OpenAIAdapter
from .grok_adapter import GrokAdapter
from .deepseek_adapter import DeepSeekAdapter
from .model_router import ModelRouter, ComplexityTier, ClassificationResult


# Provider name to adapter class mapping
PROVIDER_ADAPTERS = {
    "anthropic": AnthropicAdapter,
    "openai": OpenAIAdapter,
    "deepseek": DeepSeekAdapter,
    "xai": GrokAdapter,
}

# Default models per provider (updated Jan 2026)
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "deepseek": "deepseek-chat",
    "xai": "grok-4-1",  # Most intelligent, #1 LMArena
}

# Default fallback order - Anthropic (Claude Sonnet) first for best quality
DEFAULT_FALLBACK_ORDER = ["anthropic", "openai", "xai", "deepseek"]


class UnifiedLLMClient:
    """Unified LLM client with automatic fallback and intelligent routing.

    Example usage:
        client = UnifiedLLMClient()
        response = client.create_message(
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=1024,
            system="You are a helpful assistant.",
            tools=[...]
        )

        for block in response.content:
            if isinstance(block, TextBlock):
                print(block.text)
            elif isinstance(block, ToolCall):
                execute_tool(block.name, block.input)

    Intelligent Routing:
        client = UnifiedLLMClient(use_router=True)
        response = client.create_message_routed(
            prompt="Create an S3 bucket",  # Classified as SIMPLE -> uses gpt-4o-mini
            messages=[...],
            ...
        )
    """

    def __init__(
        self,
        fallback_order: list[str] | None = None,
        models: dict[str, str] | None = None,
        api_keys: dict[str, str] | None = None,
        use_router: bool = False,
        force_tier: Optional[ComplexityTier] = None,
    ):
        """Initialize unified client.

        Args:
            fallback_order: Order to try providers (default: anthropic, xai, openai)
            models: Provider -> model mapping override
            api_keys: Provider -> API key mapping override
            use_router: Enable intelligent model routing based on prompt complexity
            force_tier: Force a specific complexity tier (for testing)
        """
        self.fallback_order = fallback_order or DEFAULT_FALLBACK_ORDER
        self.models = {**DEFAULT_MODELS, **(models or {})}
        self.api_keys = api_keys or {}
        self.use_router = use_router

        # Initialize adapters
        self._adapters: dict[
            str, AnthropicAdapter | GrokAdapter | OpenAIAdapter | DeepSeekAdapter
        ] = {}
        for provider in self.fallback_order:
            if provider in PROVIDER_ADAPTERS:
                adapter_class = PROVIDER_ADAPTERS[provider]
                api_key = self.api_keys.get(provider)
                default_model = self.models.get(provider)
                self._adapters[provider] = adapter_class(
                    api_key=api_key, default_model=default_model
                )

        # Initialize router if enabled
        self._router: Optional[ModelRouter] = None
        if use_router:
            available = self.get_available_providers()
            self._router = ModelRouter(
                available_providers=available,
                force_tier=force_tier,
            )

        # Track last classification for debugging
        self._last_classification: Optional[ClassificationResult] = None

    def get_available_providers(self) -> list[str]:
        """Get list of providers with API keys configured."""
        return [
            provider
            for provider in self.fallback_order
            if provider in self._adapters and self._adapters[provider].is_available()
        ]

    def create_message(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 8096,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        preferred_provider: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Create a message using available providers with automatic fallback.

        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens in response
            system: System prompt
            tools: List of tools in Anthropic format
            preferred_provider: Try this provider first (still falls back on error)
            **kwargs: Additional arguments passed to adapters

        Returns:
            Normalized LLMResponse

        Raises:
            NoAvailableProviderError: If all providers fail
        """
        # Determine provider order
        providers_to_try = list(self.fallback_order)
        if preferred_provider and preferred_provider in providers_to_try:
            providers_to_try.remove(preferred_provider)
            providers_to_try.insert(0, preferred_provider)

        errors: list[tuple[str, Exception]] = []
        skipped_providers: set[str] = set()
        unavailable_providers: list[str] = []

        for provider in providers_to_try:
            if provider in skipped_providers:
                continue

            adapter = self._adapters.get(provider)
            if not adapter:
                continue

            if not adapter.is_available():
                unavailable_providers.append(provider)
                skipped_providers.add(provider)
                continue

            try:
                model = self.models.get(provider)
                return adapter.create_message(
                    messages=messages,
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    tools=tools,
                    **kwargs,
                )

            except AuthenticationError as e:
                # Authentication errors mean we should skip this provider entirely
                skipped_providers.add(provider)
                errors.append((provider, e))
                continue

            except (RateLimitError, APIError, TimeoutError) as e:
                # Retryable errors - try next provider
                errors.append((provider, e))
                continue

        # All providers failed
        raise NoAvailableProviderError(errors, unavailable_providers)

    def create_message_routed(
        self,
        prompt: str,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 8096,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Create a message using intelligent model routing.

        Classifies the prompt complexity and selects the most cost-effective
        model that can handle the task. Falls back to higher-tier models
        on failure.

        Args:
            prompt: The user's original prompt (for classification)
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens in response
            system: System prompt
            tools: List of tools in Anthropic format
            **kwargs: Additional arguments passed to adapters

        Returns:
            Normalized LLMResponse with model selection info

        Raises:
            NoAvailableProviderError: If all providers/models fail
        """
        if not self._router:
            # Router not enabled, use default behavior
            return self.create_message(
                messages=messages,
                max_tokens=max_tokens,
                system=system,
                tools=tools,
                **kwargs,
            )

        # Get recommended model from router
        model_config, classification = self._router.select_model(prompt)
        self._last_classification = classification

        # Ensure we have an adapter for this provider
        if model_config.provider not in self._adapters:
            # Initialize adapter on demand
            if model_config.provider in PROVIDER_ADAPTERS:
                adapter_class = PROVIDER_ADAPTERS[model_config.provider]
                self._adapters[model_config.provider] = adapter_class(
                    default_model=model_config.model
                )

        # Try selected model
        try:
            adapter = self._adapters.get(model_config.provider)
            if adapter and adapter.is_available():
                return adapter.create_message(
                    messages=messages,
                    model=model_config.model,
                    max_tokens=max_tokens,
                    system=system,
                    tools=tools,
                    **kwargs,
                )
        except (APIError, RateLimitError, TimeoutError):
            pass  # Fall through to fallback

        # Try fallback model
        fallback = self._router.get_fallback_model(model_config, prompt)
        if fallback:
            adapter = self._adapters.get(fallback.provider)
            if adapter and adapter.is_available():
                return adapter.create_message(
                    messages=messages,
                    model=fallback.model,
                    max_tokens=max_tokens,
                    system=system,
                    tools=tools,
                    **kwargs,
                )

        # Ultimate fallback: use default create_message behavior
        return self.create_message(
            messages=messages,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            **kwargs,
        )

    def classify_prompt(self, prompt: str) -> Optional[ClassificationResult]:
        """Classify a prompt without making an API call.

        Args:
            prompt: The user's infrastructure request.

        Returns:
            ClassificationResult or None if router not enabled.
        """
        if self._router:
            return self._router.classify_prompt(prompt)
        return None

    def get_last_classification(self) -> Optional[ClassificationResult]:
        """Get the classification result from the last routed call."""
        return self._last_classification

    def get_routing_stats(self) -> dict:
        """Get model routing statistics."""
        if self._router:
            return self._router.get_stats()
        return {"router_enabled": False}
