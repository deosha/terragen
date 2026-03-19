"""
TerraGen Agent - Agentic loop implementation using unified LLM client.
"""

from pathlib import Path
from typing import Optional, Callable, Any
from datetime import datetime

from rich.console import Console
from rich.prompt import Prompt

from .config import SYSTEM_PROMPT, LLM_MODELS, FALLBACK_ORDER
from .llm import UnifiedLLMClient, TextBlock, ToolCall, StopReason
from .tools import TOOLS, execute_tool

console = Console()


# Event callback type for streaming events to UI
EventCallback = Callable[[dict[str, Any]], None]


class TerraGenAgent:
    """Agent that maintains conversation state for continuous refinement."""

    def __init__(
        self,
        output_dir: Path,
        system_prompt: str = SYSTEM_PROMPT,
        event_callback: Optional[EventCallback] = None,
        preferred_provider: Optional[str] = None,
    ):
        self.client = UnifiedLLMClient(
            fallback_order=FALLBACK_ORDER,
            models=LLM_MODELS,
        )
        self.messages = []
        self.output_dir = output_dir
        self.system_prompt = system_prompt
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_creation_tokens = 0
        self.total_cache_read_tokens = 0
        self._current_provider = None
        self.event_callback = event_callback
        self.preferred_provider = preferred_provider

    def _emit_event(
        self, event_type: str, message: str, level: str = "info", details: str = None
    ):
        """Emit an event to the callback if registered."""
        if self.event_callback:
            event = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": level,
                "message": message,
            }
            if details:
                event["details"] = details
            self.event_callback({"log": event})

    def chat(self, user_message: str, max_turns: int = 50) -> str:
        """Send a message and get response. Maintains conversation history."""

        self.messages.append({"role": "user", "content": user_message})

        for turn in range(max_turns):
            console.print(f"[dim]Turn {turn + 1}...[/dim]")
            self._emit_event("turn", f"Processing turn {turn + 1}...")

            response = self.client.create_message(
                max_tokens=8096,
                system=self.system_prompt,
                tools=TOOLS,
                messages=self.messages,
                preferred_provider=self.preferred_provider,
            )

            # Track provider and token usage (including cache stats)
            self._current_provider = response.provider
            self.total_input_tokens += response.usage.input_tokens
            self.total_output_tokens += response.usage.output_tokens
            self.total_cache_creation_tokens += (
                response.usage.cache_creation_input_tokens
            )
            self.total_cache_read_tokens += response.usage.cache_read_input_tokens

            # Log model info on first turn
            if turn == 0:
                cache_info = ""
                if response.usage.cache_read_input_tokens > 0:
                    cache_info = (
                        f" (cache hit: {response.usage.cache_read_input_tokens} tokens)"
                    )
                elif response.usage.cache_creation_input_tokens > 0:
                    cache_info = f" (cache write: {response.usage.cache_creation_input_tokens} tokens)"
                self._emit_event(
                    "model",
                    f"Using {response.provider}/{response.model}{cache_info}",
                    level="info",
                )

            # Process response
            assistant_content = []
            tool_results = []

            for block in response.content:
                if isinstance(block, TextBlock):
                    console.print(block.text)
                    # Emit text blocks that look like status updates (short lines)
                    text = block.text.strip()
                    if text and len(text) < 200:
                        self._emit_event("text", text)
                    assistant_content.append({"type": "text", "text": block.text})

                elif isinstance(block, ToolCall):
                    console.print(f"[yellow]Tool: {block.name}[/yellow]")

                    # Build tool description for logging
                    if block.name == "write_file":
                        path = block.input.get("path", "")
                        filename = Path(path).name if path else "unknown"
                        console.print(f"[dim]  → {path}[/dim]")
                        self._emit_event(
                            "tool", f"Writing file: {filename}", details=path
                        )
                    elif block.name == "run_command":
                        cmd = block.input.get("command", "")[:60]
                        console.print(f"[dim]  → {cmd}...[/dim]")
                        self._emit_event("tool", f"Running: {cmd}")
                    elif block.name == "read_file":
                        path = block.input.get("path", "")
                        filename = Path(path).name if path else "unknown"
                        self._emit_event("tool", f"Reading file: {filename}")
                    elif block.name == "list_files":
                        self._emit_event("tool", "Listing files")
                    else:
                        self._emit_event("tool", f"Tool: {block.name}")

                    result = execute_tool(block.name, block.input)

                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            self.messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == StopReason.END_TURN:
                return "Success"

            if tool_results:
                self.messages.append({"role": "user", "content": tool_results})
            else:
                break

        return "Reached max turns"

    def get_usage(self) -> dict:
        """Get token usage statistics with cache savings."""
        # Sonnet pricing: $3/1M input, $15/1M output
        # Cache reads cost 10% of normal input price = $0.30/1M
        # Cache writes have 25% surcharge = $3.75/1M
        base_input_cost = self.total_input_tokens * 3 / 1_000_000
        output_cost = self.total_output_tokens * 15 / 1_000_000

        # Calculate cache savings (90% off for cache reads)
        cache_savings = self.total_cache_read_tokens * 3 * 0.9 / 1_000_000

        # Actual cost = base - savings + small write premium
        cache_write_premium = self.total_cache_creation_tokens * 3 * 0.25 / 1_000_000
        actual_cost = (
            base_input_cost + output_cost - cache_savings + cache_write_premium
        )

        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "cache_creation_tokens": self.total_cache_creation_tokens,
            "cache_read_tokens": self.total_cache_read_tokens,
            "estimated_cost_usd": actual_cost,
            "estimated_savings_usd": cache_savings,
        }


def run_agent(
    prompt: str,
    output_dir: Path,
    system_prompt: str = SYSTEM_PROMPT,
    max_turns: int = 50,
    event_callback: Optional[EventCallback] = None,
    preferred_provider: Optional[str] = None,
) -> str:
    """Run the agentic loop until completion or max turns (single-shot mode)."""
    agent = TerraGenAgent(
        output_dir,
        system_prompt,
        event_callback=event_callback,
        preferred_provider=preferred_provider,
    )
    available = agent.client.get_available_providers()
    console.print(f"\n[dim]Available providers: {', '.join(available)}[/dim]")
    if event_callback:
        event_callback(
            {
                "log": {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "level": "info",
                    "message": f"Using LLM providers: {', '.join(available)}",
                }
            }
        )
    return agent.chat(prompt, max_turns)


def run_interactive_session(
    initial_prompt: str, output_dir: Path, system_prompt: str = SYSTEM_PROMPT
) -> None:
    """Run interactive session allowing continuous refinement."""
    agent = TerraGenAgent(output_dir, system_prompt)

    available = agent.client.get_available_providers()
    console.print(f"\n[dim]Available providers: {', '.join(available)}[/dim]")
    console.print("[dim]Interactive mode: Type your changes or 'quit' to exit[/dim]\n")

    # Initial generation
    agent.chat(initial_prompt)

    # Continue conversation
    while True:
        console.print("\n" + "─" * 50)
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            break

        if user_input.lower() in ["quit", "exit", "q"]:
            break

        if not user_input.strip():
            continue

        console.print()
        agent.chat(user_input)

    # Show usage
    usage = agent.get_usage()
    console.print(
        f"\n[dim]Session usage: {usage['total_tokens']:,} tokens (~${usage['estimated_cost_usd']:.4f})[/dim]"
    )
