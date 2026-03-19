"""
TerraGen Tools - Tool definitions and execution for Claude.
"""

import subprocess
from pathlib import Path

# Tool definitions for Claude
TOOLS = [
    {
        "name": "write_file",
        "description": "Write content to a file. Creates parent directories if needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "content": {"type": "string", "description": "Content to write"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "read_file",
        "description": "Read content from a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "run_command",
        "description": "Run a shell command and return output.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to run"},
                "cwd": {"type": "string", "description": "Working directory (optional)"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "list_files",
        "description": "List files in a directory matching a pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"},
                "pattern": {"type": "string", "description": "Glob pattern (e.g., '*.tf')", "default": "*"}
            },
            "required": ["path"]
        }
    }
]


def execute_tool(name: str, inputs: dict) -> str:
    """Execute a tool and return the result."""
    try:
        if name == "write_file":
            path = Path(inputs["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(inputs["content"])
            return f"Successfully written to {path}"

        elif name == "read_file":
            path = Path(inputs["path"])
            if not path.exists():
                return f"Error: File not found: {path}"
            content = path.read_text()
            # Limit content to avoid token overflow
            if len(content) > 10000:
                content = content[:10000] + "\n... (truncated)"
            return content

        elif name == "run_command":
            cwd = inputs.get("cwd")
            result = subprocess.run(
                inputs["command"],
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=120
            )
            output = result.stdout + result.stderr
            # Limit output
            if len(output) > 5000:
                output = output[:5000] + "\n... (truncated)"
            return output if output else "(no output)"

        elif name == "list_files":
            path = Path(inputs["path"])
            pattern = inputs.get("pattern", "*")
            if not path.exists():
                return f"Error: Directory not found: {path}"
            files = list(path.rglob(pattern))[:50]  # Limit results
            return "\n".join(str(f) for f in files) if files else "(no files found)"

        else:
            return f"Error: Unknown tool: {name}"

    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 120 seconds"
    except Exception as e:
        return f"Error: {str(e)}"
