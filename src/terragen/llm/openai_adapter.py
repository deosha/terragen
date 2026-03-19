"""
OpenAI GPT adapter for unified LLM interface.
"""

import json
import os
from typing import Any

from openai import OpenAI, APIError as OpenAIAPIError, AuthenticationError as OpenAIAuthError
from openai import RateLimitError as OpenAIRateLimitError, APITimeoutError as OpenAITimeoutError

from .base import LLMResponse, TextBlock, ToolCall, StopReason, Usage
from .exceptions import APIError, AuthenticationError, RateLimitError, TimeoutError
from .tool_converter import anthropic_to_openai


class OpenAIAdapter:
    """Adapter for OpenAI GPT API."""

    PROVIDER_NAME = "openai"

    def __init__(self, api_key: str | None = None, default_model: str = "gpt-4o"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.default_model = default_model
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """Lazy initialization of client."""
        if self._client is None:
            if not self.api_key:
                raise AuthenticationError("OPENAI_API_KEY not set", self.PROVIDER_NAME)
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def is_available(self) -> bool:
        """Check if this provider is available (has API key)."""
        return bool(self.api_key or os.environ.get("OPENAI_API_KEY"))

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
        """Create a message using OpenAI API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (default: gpt-5-2)
            max_tokens: Maximum tokens in response
            system: System prompt
            tools: List of tools in Anthropic format (will be converted)
            **kwargs: Additional arguments passed to API

        Returns:
            Normalized LLMResponse
        """
        model = model or self.default_model

        try:
            # Convert messages to OpenAI format
            openai_messages = self._convert_messages(messages, system)

            api_kwargs: dict[str, Any] = {
                "model": model,
                "messages": openai_messages,
            }

            # GPT-5 models use max_completion_tokens instead of max_tokens
            if model.startswith("gpt-5") or model.startswith("o1") or model.startswith("o3"):
                api_kwargs["max_completion_tokens"] = max_tokens
            else:
                api_kwargs["max_tokens"] = max_tokens

            # Convert tools from Anthropic to OpenAI format
            if tools:
                api_kwargs["tools"] = anthropic_to_openai(tools)

            response = self.client.chat.completions.create(**api_kwargs)
            return self._normalize_response(response, model)

        except OpenAIAuthError as e:
            raise AuthenticationError(str(e), self.PROVIDER_NAME)
        except OpenAIRateLimitError as e:
            raise RateLimitError(str(e), self.PROVIDER_NAME)
        except OpenAITimeoutError as e:
            raise TimeoutError(str(e), self.PROVIDER_NAME)
        except OpenAIAPIError as e:
            raise APIError(str(e), self.PROVIDER_NAME, getattr(e, "status_code", None))

    def _convert_messages(
        self,
        messages: list[dict[str, Any]],
        system: str | None
    ) -> list[dict[str, Any]]:
        """Convert Anthropic-style messages to OpenAI format."""
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
                            openai_messages.append({
                                "role": "tool",
                                "tool_call_id": item["tool_use_id"],
                                "content": item["content"]
                            })
                        elif item.get("type") == "text":
                            openai_messages.append({
                                "role": "user",
                                "content": item["text"]
                            })
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
                            tool_calls.append({
                                "id": item["id"],
                                "type": "function",
                                "function": {
                                    "name": item["name"],
                                    "arguments": json.dumps(item["input"])
                                }
                            })

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

    def _normalize_response(self, response: Any, model: str) -> LLMResponse:
        """Convert OpenAI response to normalized LLMResponse."""
        content: list[TextBlock | ToolCall] = []
        choice = response.choices[0]
        message = choice.message

        # Add text content if present
        if message.content:
            content.append(TextBlock(text=message.content))

        # Add tool calls if present
        if message.tool_calls:
            for tool_call in message.tool_calls:
                # Parse arguments - handle potential JSON errors
                try:
                    args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                except json.JSONDecodeError:
                    # If JSON parsing fails, try to use as-is or empty dict
                    args = {"raw_args": tool_call.function.arguments} if tool_call.function.arguments else {}

                content.append(ToolCall(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    input=args
                ))

        # Ensure we have at least some content
        if not content:
            content.append(TextBlock(text=""))

        # Map finish reason to stop reason
        finish_reason_map = {
            "stop": StopReason.END_TURN,
            "tool_calls": StopReason.TOOL_USE,
            "function_call": StopReason.TOOL_USE,  # Older API format
            "length": StopReason.MAX_TOKENS,
            "content_filter": StopReason.END_TURN,
        }
        stop_reason = finish_reason_map.get(choice.finish_reason, StopReason.UNKNOWN)

        # Extract cache usage if available (OpenAI automatic caching)
        cache_read_tokens = 0
        if response.usage and hasattr(response.usage, "prompt_tokens_details"):
            details = response.usage.prompt_tokens_details
            if details and hasattr(details, "cached_tokens"):
                cache_read_tokens = details.cached_tokens or 0

        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            usage=Usage(
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
                cache_creation_input_tokens=0,  # OpenAI doesn't report this separately
                cache_read_input_tokens=cache_read_tokens,
            ),
            provider=self.PROVIDER_NAME,
            model=model,
            raw_response=response
        )
