"""
Anthropic Claude adapter for unified LLM interface.

Supports prompt caching for cost optimization:
- System prompts are cached with 5-minute TTL
- Tools are cached with 5-minute TTL
- Cached tokens cost 90% less on cache hits

See: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
"""

import os
from typing import Any

from anthropic import Anthropic, APIError as AnthropicAPIError, AuthenticationError as AnthropicAuthError
from anthropic import RateLimitError as AnthropicRateLimitError, APITimeoutError as AnthropicTimeoutError

from .base import LLMResponse, TextBlock, ToolCall, StopReason, Usage
from .exceptions import APIError, AuthenticationError, RateLimitError, TimeoutError


class AnthropicAdapter:
    """Adapter for Anthropic Claude API with prompt caching support."""

    PROVIDER_NAME = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str = "claude-sonnet-4-20250514",
        enable_cache: bool = True,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.default_model = default_model
        self.enable_cache = enable_cache
        self._client: Anthropic | None = None

    @property
    def client(self) -> Anthropic:
        """Lazy initialization of client."""
        if self._client is None:
            if not self.api_key:
                raise AuthenticationError("ANTHROPIC_API_KEY not set", self.PROVIDER_NAME)
            self._client = Anthropic(api_key=self.api_key)
        return self._client

    def is_available(self) -> bool:
        """Check if this provider is available (has API key)."""
        return bool(self.api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def create_message(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 8096,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        **kwargs
    ) -> LLMResponse:
        """Create a message using Anthropic API with optional prompt caching.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (default: claude-sonnet-4-20250514)
            max_tokens: Maximum tokens in response
            system: System prompt (will be cached if enable_cache=True)
            tools: List of tools in Anthropic format (will be cached if enable_cache=True)
            **kwargs: Additional arguments passed to API

        Returns:
            Normalized LLMResponse

        Note:
            When caching is enabled, system prompts and tools are marked with
            cache_control blocks. Cached tokens have 90% cost reduction on hits.
            Cache TTL is 5 minutes (ephemeral).
        """
        model = model or self.default_model

        try:
            api_kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
            }

            # Add system prompt with caching if enabled
            if system:
                if self.enable_cache:
                    # Use cached system prompt format
                    api_kwargs["system"] = [
                        {
                            "type": "text",
                            "text": system,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]
                else:
                    api_kwargs["system"] = system

            # Add tools with caching on the last tool if enabled
            if tools:
                if self.enable_cache and len(tools) > 0:
                    # Add cache_control to the last tool (per Anthropic docs)
                    cached_tools = []
                    for i, tool in enumerate(tools):
                        tool_copy = dict(tool)
                        if i == len(tools) - 1:
                            # Mark last tool for caching
                            tool_copy["cache_control"] = {"type": "ephemeral"}
                        cached_tools.append(tool_copy)
                    api_kwargs["tools"] = cached_tools
                else:
                    api_kwargs["tools"] = tools

            api_kwargs.update(kwargs)

            response = self.client.messages.create(**api_kwargs)
            return self._normalize_response(response, model)

        except AnthropicAuthError as e:
            raise AuthenticationError(str(e), self.PROVIDER_NAME)
        except AnthropicRateLimitError as e:
            raise RateLimitError(str(e), self.PROVIDER_NAME)
        except AnthropicTimeoutError as e:
            raise TimeoutError(str(e), self.PROVIDER_NAME)
        except AnthropicAPIError as e:
            raise APIError(str(e), self.PROVIDER_NAME, getattr(e, "status_code", None))

    def _normalize_response(self, response: Any, model: str) -> LLMResponse:
        """Convert Anthropic response to normalized LLMResponse with cache usage."""
        content: list[TextBlock | ToolCall] = []

        for block in response.content:
            if block.type == "text":
                content.append(TextBlock(text=block.text))
            elif block.type == "tool_use":
                content.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    input=block.input
                ))

        # Map stop reason
        stop_reason_map = {
            "end_turn": StopReason.END_TURN,
            "tool_use": StopReason.TOOL_USE,
            "max_tokens": StopReason.MAX_TOKENS,
            "stop_sequence": StopReason.STOP_SEQUENCE,
        }
        stop_reason = stop_reason_map.get(response.stop_reason, StopReason.UNKNOWN)

        # Extract cache usage if available (Anthropic prompt caching)
        cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0

        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            usage=Usage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_creation_input_tokens=cache_creation,
                cache_read_input_tokens=cache_read,
            ),
            provider=self.PROVIDER_NAME,
            model=model,
            raw_response=response
        )
