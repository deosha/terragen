# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is TerraGen

AI-powered Terraform code generator. Takes natural language prompts (or architecture diagram images) and produces production-ready Terraform code via a multi-agent pipeline. Supports AWS, GCP, and Azure with multi-LLM backend (OpenAI, Anthropic, xAI, DeepSeek).

## Project Structure

Three main components:

- **`src/terragen/`** — Core Python package (CLI + library). Entry point: `cli.py` → `terragen` command.
- **`api/`** — FastAPI backend (`api/main.py`). Routes in `api/routes/`. OAuth via `api/auth.py`.
- **`web/`** — Next.js frontend (React, Tailwind). Pages in `web/src/app/`, components in `web/src/components/`.

### Core Package (`src/terragen/`)

- `agents/` — Multi-agent pipeline: `orchestrator.py` coordinates `clarification.py` → `code_generation.py` → `validation.py` → `cost.py`. Each agent extends `base.py`. Also includes `security.py`, `checkov.py`, `fast_security.py`, `policy.py`, `visualization.py`.
- `llm/` — Unified LLM client (`client.py`) with provider adapters (`anthropic_adapter.py`, `openai_adapter.py`, `grok_adapter.py`, `deepseek_adapter.py`). `model_router.py` handles complexity-based routing. `tool_converter.py` normalizes tool calling across providers.
- `security/` — Pattern-based security scanner (`pattern_scanner.py`) with rules in `security/rules/`.
- `generator.py` — High-level `generate_terraform()` and `generate_terraform_pipeline()`.
- `modifier.py` — Modify existing Terraform repos.
- `vision.py` — Architecture diagram analysis (Claude Vision).
- `questions.py` — Clarifying questions generation.
- `tools.py` — Tool execution (write_file, read_file, run_command) for agent tool-use.
- `config.py` — Configuration, prompts, constants.

## Commands

### Install

```bash
pip install -e .              # CLI only
pip install -e ".[api]"       # CLI + API
pip install -e ".[dev]"       # CLI + dev tools
cd web && npm install          # Frontend
```

### Run

```bash
./start.sh                     # Start API (port 8000) + Frontend (port 3000)
uvicorn api.main:app --reload  # API only
cd web && npm run dev          # Frontend only
```

### Test

```bash
pytest                         # All tests
pytest tests/test_cli.py       # Single test file
pytest -k "test_name"          # Single test by name
pytest -m "not slow"           # Skip slow tests
```

### Lint/Format

```bash
black src/ tests/ api/         # Format Python code
mypy src/                      # Type check
```

### CLI Usage

```bash
terragen generate "VPC with EKS" -o ./output -p aws -r us-east-1
```

## Key Architecture Details

- **Multi-agent pipeline** flows: Clarify → CodeGen → Validate → Cost. The orchestrator (`agents/orchestrator.py`) manages this sequence with SSE progress events sent to the web UI.
- **Agentic fix loop**: When `terraform validate` fails, the validation agent sends errors back to the LLM for auto-fix, up to 3 retries.
- **LLM abstraction**: `UnifiedLLMClient` in `llm/client.py` provides a single interface across all providers. Provider adapters normalize chat/tool-calling APIs. Automatic fallback between providers.
- **Model router** (`llm/model_router.py`): Scores prompt complexity (0-100) and routes to appropriate model tier (cheap for simple, expensive for complex).
- **Prompt caching**: Anthropic adapter uses prompt caching for system prompts/tools (90% cost reduction on cache hits).
- **Security scanning** is on-demand (not in the default pipeline): tfsec, Checkov, Conftest, and a built-in pattern scanner.
- **OPA policies** live in `policies/terraform.rego` for Conftest.

## Environment

- Python 3.10+, Node.js 18+
- Requires at least one LLM API key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `XAI_API_KEY`, or `DEEPSEEK_API_KEY`)
- Terraform CLI must be installed for validation/plan stages
- `.env` file at project root for all config (copy `.env.example`)
