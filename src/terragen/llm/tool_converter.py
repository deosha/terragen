"""
Tool schema converter for different LLM providers.

Converts between Anthropic tool format and OpenAI/Grok function format.
"""

from typing import Any


def anthropic_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Anthropic tool schema to OpenAI/Grok function format.

    Anthropic format:
        {
            "name": "write_file",
            "description": "Write content to a file",
            "input_schema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }

    OpenAI/Grok format:
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Write content to a file",
                "parameters": {
                    "type": "object",
                    "properties": {...},
                    "required": [...]
                }
            }
        }
    """
    if not tools:
        return []

    converted = []
    for tool in tools:
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get(
                    "input_schema", {"type": "object", "properties": {}, "required": []}
                ),
            },
        }
        converted.append(openai_tool)

    return converted


def openai_to_anthropic(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert OpenAI function format to Anthropic tool schema.

    Reverse of anthropic_to_openai.
    """
    if not tools:
        return []

    converted = []
    for tool in tools:
        if tool.get("type") == "function":
            func = tool["function"]
            anthropic_tool = {
                "name": func["name"],
                "description": func.get("description", ""),
                "input_schema": func.get(
                    "parameters", {"type": "object", "properties": {}, "required": []}
                ),
            }
            converted.append(anthropic_tool)

    return converted
