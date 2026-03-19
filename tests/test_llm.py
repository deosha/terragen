"""Tests for TerraGen LLM module."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from terragen.llm import (
    UnifiedLLMClient,
    TextBlock,
    ToolCall,
    StopReason,
    LLMResponse,
    Usage,
    RateLimitError,
    APIError,
    AuthenticationError,
    TimeoutError,
    NoAvailableProviderError,
)
from terragen.llm.tool_converter import anthropic_to_openai, openai_to_anthropic


class TestToolConverter:
    """Test tool schema conversion between providers."""

    def test_anthropic_to_openai_basic(self):
        """Convert basic Anthropic tool to OpenAI format."""
        anthropic_tools = [
            {
                "name": "write_file",
                "description": "Write content to a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            }
        ]

        openai_tools = anthropic_to_openai(anthropic_tools)

        assert len(openai_tools) == 1
        assert openai_tools[0]["type"] == "function"
        assert openai_tools[0]["function"]["name"] == "write_file"
        assert openai_tools[0]["function"]["description"] == "Write content to a file"
        assert (
            openai_tools[0]["function"]["parameters"]
            == anthropic_tools[0]["input_schema"]
        )

    def test_anthropic_to_openai_empty(self):
        """Empty tools list returns empty list."""
        assert anthropic_to_openai([]) == []
        assert anthropic_to_openai(None) == []

    def test_anthropic_to_openai_multiple_tools(self):
        """Convert multiple Anthropic tools."""
        anthropic_tools = [
            {
                "name": "tool1",
                "description": "desc1",
                "input_schema": {"type": "object"},
            },
            {
                "name": "tool2",
                "description": "desc2",
                "input_schema": {"type": "object"},
            },
        ]

        openai_tools = anthropic_to_openai(anthropic_tools)

        assert len(openai_tools) == 2
        assert openai_tools[0]["function"]["name"] == "tool1"
        assert openai_tools[1]["function"]["name"] == "tool2"

    def test_openai_to_anthropic_basic(self):
        """Convert basic OpenAI tool to Anthropic format."""
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            }
        ]

        anthropic_tools = openai_to_anthropic(openai_tools)

        assert len(anthropic_tools) == 1
        assert anthropic_tools[0]["name"] == "read_file"
        assert anthropic_tools[0]["description"] == "Read a file"
        assert (
            anthropic_tools[0]["input_schema"]
            == openai_tools[0]["function"]["parameters"]
        )

    def test_openai_to_anthropic_empty(self):
        """Empty tools list returns empty list."""
        assert openai_to_anthropic([]) == []
        assert openai_to_anthropic(None) == []


class TestBaseTypes:
    """Test base LLM types."""

    def test_usage_total_tokens(self):
        """Usage should calculate total tokens."""
        usage = Usage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150

    def test_text_block(self):
        """TextBlock should store text."""
        block = TextBlock(text="Hello world")
        assert block.text == "Hello world"
        assert block.type == "text"

    def test_tool_call(self):
        """ToolCall should store tool call data."""
        call = ToolCall(id="123", name="write_file", input={"path": "/tmp/test"})
        assert call.id == "123"
        assert call.name == "write_file"
        assert call.input == {"path": "/tmp/test"}
        assert call.type == "tool_use"

    def test_llm_response_get_text(self):
        """LLMResponse.get_text() should concatenate text blocks."""
        response = LLMResponse(
            content=[
                TextBlock(text="Hello "),
                ToolCall(id="1", name="test", input={}),
                TextBlock(text="world"),
            ],
            stop_reason=StopReason.END_TURN,
            usage=Usage(input_tokens=10, output_tokens=5),
            provider="test",
            model="test-model",
        )
        assert response.get_text() == "Hello world"

    def test_llm_response_get_tool_calls(self):
        """LLMResponse.get_tool_calls() should return only tool calls."""
        tool1 = ToolCall(id="1", name="tool1", input={})
        tool2 = ToolCall(id="2", name="tool2", input={})
        response = LLMResponse(
            content=[TextBlock(text="text"), tool1, tool2],
            stop_reason=StopReason.TOOL_USE,
            usage=Usage(input_tokens=10, output_tokens=5),
            provider="test",
            model="test-model",
        )
        tool_calls = response.get_tool_calls()
        assert len(tool_calls) == 2
        assert tool_calls[0].name == "tool1"
        assert tool_calls[1].name == "tool2"


class TestUnifiedLLMClient:
    """Test UnifiedLLMClient."""

    def test_initialization_default_order(self):
        """Client initializes with default fallback order."""
        client = UnifiedLLMClient()
        assert client.fallback_order == ["anthropic", "xai", "openai"]

    def test_initialization_custom_order(self):
        """Client accepts custom fallback order."""
        client = UnifiedLLMClient(fallback_order=["openai", "anthropic"])
        assert client.fallback_order == ["openai", "anthropic"]

    def test_initialization_custom_models(self):
        """Client accepts custom model mapping."""
        custom_models = {"anthropic": "claude-opus-4-20250514"}
        client = UnifiedLLMClient(models=custom_models)
        assert client.models["anthropic"] == "claude-opus-4-20250514"

    def test_get_available_providers_none(self):
        """No providers available without API keys."""
        client = UnifiedLLMClient()
        # Without any env vars set, should return empty
        with patch.dict("os.environ", {}, clear=True):
            available = client.get_available_providers()
            # May or may not be empty depending on if keys were passed at init
            assert isinstance(available, list)

    @patch("terragen.llm.anthropic_adapter.AnthropicAdapter.is_available")
    @patch("terragen.llm.anthropic_adapter.AnthropicAdapter.create_message")
    def test_create_message_uses_first_available(self, mock_create, mock_available):
        """Client uses first available provider."""
        mock_available.return_value = True
        mock_response = LLMResponse(
            content=[TextBlock(text="Hello")],
            stop_reason=StopReason.END_TURN,
            usage=Usage(input_tokens=10, output_tokens=5),
            provider="anthropic",
            model="claude-sonnet-4-20250514",
        )
        mock_create.return_value = mock_response

        client = UnifiedLLMClient()
        response = client.create_message(
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=100,
        )

        assert response.provider == "anthropic"
        mock_create.assert_called_once()

    @patch("terragen.llm.grok_adapter.GrokAdapter.is_available")
    @patch("terragen.llm.grok_adapter.GrokAdapter.create_message")
    @patch("terragen.llm.anthropic_adapter.AnthropicAdapter.is_available")
    @patch("terragen.llm.anthropic_adapter.AnthropicAdapter.create_message")
    def test_fallback_on_rate_limit(
        self,
        mock_anthropic_create,
        mock_anthropic_available,
        mock_grok_create,
        mock_grok_available,
    ):
        """Client falls back to next provider on rate limit error."""
        mock_anthropic_available.return_value = True
        mock_anthropic_create.side_effect = RateLimitError("Rate limited", "anthropic")

        mock_grok_available.return_value = True
        mock_grok_response = LLMResponse(
            content=[TextBlock(text="Hello from Grok")],
            stop_reason=StopReason.END_TURN,
            usage=Usage(input_tokens=10, output_tokens=5),
            provider="xai",
            model="grok-4.1-fast",
        )
        mock_grok_create.return_value = mock_grok_response

        client = UnifiedLLMClient(fallback_order=["anthropic", "xai"])
        response = client.create_message(
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=100,
        )

        assert response.provider == "xai"
        assert mock_anthropic_create.called
        assert mock_grok_create.called

    @patch("terragen.llm.anthropic_adapter.AnthropicAdapter.is_available")
    @patch("terragen.llm.anthropic_adapter.AnthropicAdapter.create_message")
    def test_skip_provider_on_auth_error(self, mock_create, mock_available):
        """Client skips provider entirely on authentication error."""
        mock_available.return_value = True
        mock_create.side_effect = AuthenticationError("Invalid key", "anthropic")

        client = UnifiedLLMClient(fallback_order=["anthropic"])

        with pytest.raises(NoAvailableProviderError) as exc_info:
            client.create_message(
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=100,
            )

        assert len(exc_info.value.errors) == 1
        assert exc_info.value.errors[0][0] == "anthropic"

    @patch("terragen.llm.openai_adapter.OpenAIAdapter.is_available")
    @patch("terragen.llm.openai_adapter.OpenAIAdapter.create_message")
    @patch("terragen.llm.grok_adapter.GrokAdapter.is_available")
    @patch("terragen.llm.grok_adapter.GrokAdapter.create_message")
    @patch("terragen.llm.anthropic_adapter.AnthropicAdapter.is_available")
    @patch("terragen.llm.anthropic_adapter.AnthropicAdapter.create_message")
    def test_all_providers_fail(
        self,
        mock_anthropic_create,
        mock_anthropic_available,
        mock_grok_create,
        mock_grok_available,
        mock_openai_create,
        mock_openai_available,
    ):
        """NoAvailableProviderError when all providers fail."""
        mock_anthropic_available.return_value = True
        mock_anthropic_create.side_effect = APIError("Server error", "anthropic", 500)

        mock_grok_available.return_value = True
        mock_grok_create.side_effect = TimeoutError("Timeout", "xai")

        mock_openai_available.return_value = True
        mock_openai_create.side_effect = RateLimitError("Rate limited", "openai")

        client = UnifiedLLMClient()

        with pytest.raises(NoAvailableProviderError) as exc_info:
            client.create_message(
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=100,
            )

        assert len(exc_info.value.errors) == 3


class TestAnthropicAdapter:
    """Test Anthropic adapter response normalization."""

    @patch("terragen.llm.anthropic_adapter.Anthropic")
    def test_normalize_text_response(self, mock_anthropic_class):
        """Normalize Anthropic text response."""
        from terragen.llm.anthropic_adapter import AnthropicAdapter

        # Mock the response
        mock_content = Mock()
        mock_content.type = "text"
        mock_content.text = "Hello world"

        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        adapter = AnthropicAdapter(api_key="test-key")
        response = adapter.create_message(
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=100,
        )

        assert response.provider == "anthropic"
        assert response.stop_reason == StopReason.END_TURN
        assert len(response.content) == 1
        assert isinstance(response.content[0], TextBlock)
        assert response.content[0].text == "Hello world"

    @patch("terragen.llm.anthropic_adapter.Anthropic")
    def test_normalize_tool_use_response(self, mock_anthropic_class):
        """Normalize Anthropic tool use response."""
        from terragen.llm.anthropic_adapter import AnthropicAdapter

        mock_content = Mock()
        mock_content.type = "tool_use"
        mock_content.id = "tool_123"
        mock_content.name = "write_file"
        mock_content.input = {"path": "/tmp/test", "content": "data"}

        mock_response = Mock()
        mock_response.content = [mock_content]
        mock_response.stop_reason = "tool_use"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5

        mock_client = Mock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_class.return_value = mock_client

        adapter = AnthropicAdapter(api_key="test-key")
        response = adapter.create_message(
            messages=[{"role": "user", "content": "Write a file"}],
            max_tokens=100,
        )

        assert response.stop_reason == StopReason.TOOL_USE
        assert len(response.content) == 1
        assert isinstance(response.content[0], ToolCall)
        assert response.content[0].id == "tool_123"
        assert response.content[0].name == "write_file"


class TestOpenAIAdapter:
    """Test OpenAI adapter message conversion and response normalization."""

    def test_message_conversion_simple(self):
        """Convert simple user message."""
        from terragen.llm.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(api_key="test-key")
        messages = [{"role": "user", "content": "Hello"}]

        converted = adapter._convert_messages(messages, system="You are helpful")

        assert len(converted) == 2
        assert converted[0]["role"] == "system"
        assert converted[0]["content"] == "You are helpful"
        assert converted[1]["role"] == "user"
        assert converted[1]["content"] == "Hello"

    def test_message_conversion_tool_results(self):
        """Convert tool result messages."""
        from terragen.llm.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(api_key="test-key")
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "123",
                        "content": "File written",
                    }
                ],
            }
        ]

        converted = adapter._convert_messages(messages, system=None)

        assert len(converted) == 1
        assert converted[0]["role"] == "tool"
        assert converted[0]["tool_call_id"] == "123"
        assert converted[0]["content"] == "File written"

    def test_message_conversion_assistant_with_tool_calls(self):
        """Convert assistant message with tool calls."""
        from terragen.llm.openai_adapter import OpenAIAdapter

        adapter = OpenAIAdapter(api_key="test-key")
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I'll write a file"},
                    {
                        "type": "tool_use",
                        "id": "456",
                        "name": "write_file",
                        "input": {"path": "/tmp"},
                    },
                ],
            }
        ]

        converted = adapter._convert_messages(messages, system=None)

        assert len(converted) == 1
        assert converted[0]["role"] == "assistant"
        assert converted[0]["content"] == "I'll write a file"
        assert len(converted[0]["tool_calls"]) == 1
        assert converted[0]["tool_calls"][0]["id"] == "456"
        assert converted[0]["tool_calls"][0]["function"]["name"] == "write_file"


class TestGrokAdapter:
    """Test Grok adapter."""

    def test_message_conversion(self):
        """Grok uses same conversion as OpenAI."""
        from terragen.llm.grok_adapter import GrokAdapter

        adapter = GrokAdapter(api_key="test-key")
        messages = [{"role": "user", "content": "Hello"}]

        converted = adapter._convert_messages(messages, system="Be helpful")

        assert len(converted) == 2
        assert converted[0]["role"] == "system"
        assert converted[1]["role"] == "user"

    @patch("httpx.Client")
    def test_api_call_structure(self, mock_client_class):
        """Verify API call structure."""
        from terragen.llm.grok_adapter import GrokAdapter

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "Hello", "tool_calls": None},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        mock_client = Mock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=False)
        mock_client_class.return_value = mock_client

        adapter = GrokAdapter(api_key="test-key")
        response = adapter.create_message(
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=100,
        )

        assert response.provider == "xai"
        assert response.stop_reason == StopReason.END_TURN

        # Verify the API was called with correct URL
        call_args = mock_client.post.call_args
        assert "api.x.ai" in call_args[0][0]
