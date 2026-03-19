#!/usr/bin/env python3
"""
TerraGen - AI-powered Terraform Code Generator

This is the main entry point. The code is organized into modules:
- config.py    - Constants and configuration
- tools.py     - Tool definitions for Claude
- agent.py     - TerraGenAgent class and agentic loop
- questions.py - Interactive clarification prompts
- patterns.py  - Learn patterns from existing repos
- modifier.py  - Modify existing infrastructure
- generator.py - Main generation logic
- cli.py       - CLI commands
"""

from .cli import cli, main

if __name__ == "__main__":
    cli()
