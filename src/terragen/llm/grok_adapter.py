"""
xAI Grok adapter for unified LLM interface.

Uses httpx directly since xAI uses OpenAI-compatible API.
"""

import json
import os
from typing import Any

import httpx

from .base import LLMResponse, TextBlock, ToolCall, StopReason, Usage
from .exceptions import APIError, AuthenticationError, RateLimitError, TimeoutError
from .tool_converter import anthropic_to_openai


class GrokAdapter:
    """Adapter for xAI Grok API."""

    PROVIDER_NAME = "xai"
    BASE_URL = "https://api.x.ai/v1"

    def __init__(
        self, api_key: str | None = None, default_model: str = "grok-4-1-fast"
    ):
        """Initialize Grok adapter.

        Args:
            api_key: xAI API key (or set XAI_API_KEY env var)
            default_model: Default model to use. Options:
                - grok-4-1-fast: Best for tool calling, fast, cheap ($0.20/1M)
                - grok-4-1: Most intelligent, #1 on LMArena
                - grok-4-fast: Good balance of speed and quality
                - grok-4: Powerful reasoning model
        """
        self.api_key = api_key or os.environ.get("XAI_API_KEY")
        self.default_model = default_model

    def is_available(self) -> bool:
        """Check if this provider is available (has API key)."""
        return bool(self.api_key or os.environ.get("XAI_API_KEY"))

    def create_message(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 8096,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        timeout: float = 120.0,
        **kwargs,
    ) -> LLMResponse:
        """Create a message using xAI Grok API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (default: grok-4.1-fast)
            max_tokens: Maximum tokens in response
            system: System prompt
            tools: List of tools in Anthropic format (will be converted)
            timeout: Request timeout in seconds
            **kwargs: Additional arguments passed to API

        Returns:
            Normalized LLMResponse
        """
        if not self.api_key:
            raise AuthenticationError("XAI_API_KEY not set", self.PROVIDER_NAME)

        model = model or self.default_model

        # Convert messages to OpenAI-compatible format (Grok uses same format)
        openai_messages = self._convert_messages(messages, system)

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": openai_messages,
        }

        # Convert tools from Anthropic to OpenAI format
        if tools:
            payload["tools"] = anthropic_to_openai(tools)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    f"{self.BASE_URL}/chat/completions", headers=headers, json=payload
                )

                if response.status_code == 401:
                    raise AuthenticationError("Invalid API key", self.PROVIDER_NAME)
                elif response.status_code == 429:
                    raise RateLimitError("Rate limit exceeded", self.PROVIDER_NAME)
                elif response.status_code >= 500:
                    raise APIError(
                        f"Server error: {response.text}",
                        self.PROVIDER_NAME,
                        response.status_code,
                    )
                elif response.status_code >= 400:
                    raise APIError(
                        f"Request error: {response.text}",
                        self.PROVIDER_NAME,
                        response.status_code,
                    )

                data = response.json()
                return self._normalize_response(data, model)

        except httpx.TimeoutException as e:
            raise TimeoutError(str(e), self.PROVIDER_NAME)
        except httpx.RequestError as e:
            raise APIError(str(e), self.PROVIDER_NAME)

    def _convert_messages(
        self, messages: list[dict[str, Any]], system: str | None
    ) -> list[dict[str, Any]]:
        """Convert Anthropic-style messages to OpenAI-compatible format."""
        openai_messages = []

        # Add system message if provided
        if system:
            openai_messages.append({"role": "system", "content": system})

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                # Handle tool results
                if isinstance(content, list):
                    for item in content:
                        if item.get("type") == "tool_result":
                            openai_messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": item["tool_use_id"],
                                    "content": item["content"],
                                }
                            )
                        elif item.get("type") == "text":
                            openai_messages.append(
                                {"role": "user", "content": item["text"]}
                            )
                else:
                    openai_messages.append({"role": "user", "content": content})

            elif role == "assistant":
                # Handle assistant messages with potential tool calls
                if isinstance(content, list):
                    text_parts = []
                    tool_calls = []

                    for item in content:
                        if item.get("type") == "text":
                            text_parts.append(item["text"])
                        elif item.get("type") == "tool_use":
                            tool_calls.append(
                                {
                                    "id": item["id"],
                                    "type": "function",
                                    "function": {
                                        "name": item["name"],
                                        "arguments": json.dumps(item["input"]),
                                    },
                                }
                            )

                    assistant_msg: dict[str, Any] = {"role": "assistant"}
                    if text_parts:
                        assistant_msg["content"] = "\n".join(text_parts)
                    else:
                        assistant_msg["content"] = None
                    if tool_calls:
                        assistant_msg["tool_calls"] = tool_calls

                    openai_messages.append(assistant_msg)
                else:
                    openai_messages.append({"role": "assistant", "content": content})

        return openai_messages

    def _normalize_response(self, data: dict[str, Any], model: str) -> LLMResponse:
        """Convert Grok API response to normalized LLMResponse."""
        content: list[TextBlock | ToolCall] = []
        choice = data["choices"][0]
        message = choice["message"]

        # Add text content if present
        if message.get("content"):
            content.append(TextBlock(text=message["content"]))

        # Add tool calls if present
        if message.get("tool_calls"):
            for tool_call in message["tool_calls"]:
                content.append(
                    ToolCall(
                        id=tool_call["id"],
                        name=tool_call["function"]["name"],
                        input=json.loads(tool_call["function"]["arguments"]),
                    )
                )

        # Map finish reason to stop reason
        finish_reason = choice.get("finish_reason", "")
        finish_reason_map = {
            "stop": StopReason.END_TURN,
            "tool_calls": StopReason.TOOL_USE,
            "length": StopReason.MAX_TOKENS,
        }
        stop_reason = finish_reason_map.get(finish_reason, StopReason.UNKNOWN)

        # Parse usage
        usage_data = data.get("usage", {})

        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            usage=Usage(
                input_tokens=usage_data.get("prompt_tokens", 0),
                output_tokens=usage_data.get("completion_tokens", 0),
            ),
            provider=self.PROVIDER_NAME,
            model=model,
            raw_response=data,
        )
