"""
Base types for unified LLM interface.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StopReason(Enum):
    """Normalized stop reasons across providers."""

    END_TURN = "end_turn"
    TOOL_USE = "tool_use"
    MAX_TOKENS = "max_tokens"
    STOP_SEQUENCE = "stop_sequence"
    UNKNOWN = "unknown"


@dataclass
class Usage:
    """Token usage statistics with cache tracking."""

    input_tokens: int
    output_tokens: int
    # Cache-specific fields (Anthropic prompt caching)
    cache_creation_input_tokens: int = 0  # Tokens written to cache (first request)
    cache_read_input_tokens: int = 0  # Tokens read from cache (90% discount)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate (0.0 to 1.0)."""
        total_cacheable = (
            self.cache_creation_input_tokens + self.cache_read_input_tokens
        )
        if total_cacheable == 0:
            return 0.0
        return self.cache_read_input_tokens / total_cacheable

    @property
    def estimated_savings(self) -> float:
        """Estimate cost savings from cache hits (90% discount on cached reads)."""
        # Cache reads cost 10% of normal, so savings = 90% * cache_read_tokens
        return self.cache_read_input_tokens * 0.9


@dataclass
class TextBlock:
    """A text content block."""

    text: str
    type: str = "text"


@dataclass
class ToolCall:
    """A tool/function call request."""

    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


ContentBlock = TextBlock | ToolCall


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""

    content: list[ContentBlock]
    stop_reason: StopReason
    usage: Usage
    provider: str
    model: str
    raw_response: Any = field(default=None, repr=False)

    def get_text(self) -> str:
        """Get concatenated text from all text blocks."""
        return "".join(
            block.text for block in self.content if isinstance(block, TextBlock)
        )

    def get_tool_calls(self) -> list[ToolCall]:
        """Get all tool calls from response."""
        return [block for block in self.content if isinstance(block, ToolCall)]
