"""Tests for TerraGen CLI."""

import os
import pytest
from click.testing import CliRunner
from terragen.cli import cli


class TestCLI:
    """Test CLI commands."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_cli_help(self, runner):
        """CLI should show help."""
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "TerraGen" in result.output
        assert "generate" in result.output
        assert "validate" in result.output
        assert "cost" in result.output

    def test_cli_version(self, runner):
        """CLI should show version."""
        result = runner.invoke(cli, ["--version"])

        assert result.exit_code == 0
        assert "1.0.0" in result.output

    def test_generate_help(self, runner):
        """Generate command should show help."""
        result = runner.invoke(cli, ["generate", "--help"])

        assert result.exit_code == 0
        assert "--output" in result.output
        assert "--provider" in result.output
        assert "--region" in result.output
        assert "--interactive" in result.output
        assert "--chat" in result.output
        assert "--backend" in result.output
        assert "--modify" in result.output

    def test_validate_help(self, runner):
        """Validate command should show help."""
        result = runner.invoke(cli, ["validate", "--help"])

        assert result.exit_code == 0
        assert "DIRECTORY" in result.output

    def test_cost_help(self, runner):
        """Cost command should show help."""
        result = runner.invoke(cli, ["cost", "--help"])

        assert result.exit_code == 0
        assert "DIRECTORY" in result.output


class TestGenerateCommand:
    """Test generate command options."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_generate_requires_api_key(self, runner):
        """Generate should fail without any LLM API key."""
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("XAI_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)

        result = runner.invoke(cli, ["generate", "test prompt", "-y"], env=env)

        assert "No LLM API key" in result.output or "API key" in result.output

    def test_generate_provider_choices(self, runner):
        """Generate should only accept valid providers."""
        result = runner.invoke(cli, ["generate", "test", "-p", "invalid_provider"])

        assert result.exit_code != 0
        assert (
            "invalid_provider" in result.output.lower()
            or "invalid" in result.output.lower()
        )

    def test_generate_backend_choices(self, runner):
        """Generate should only accept valid backends."""
        result = runner.invoke(cli, ["generate", "test", "-b", "invalid_backend"])

        assert result.exit_code != 0


class TestValidateCommand:
    """Test validate command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_validate_with_directory(self, runner):
        """Validate should accept directory argument."""
        with runner.isolated_filesystem():
            os.makedirs("infra")
            with open("infra/main.tf", "w") as f:
                f.write('resource "null_resource" "test" {}')

            result = runner.invoke(cli, ["validate", "infra"])

            # Should run (may fail if terraform not installed)
            assert "Validating" in result.output


class TestCostCommand:
    """Test cost command."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_cost_without_infracost(self, runner):
        """Cost should warn if infracost not installed."""
        # This test assumes infracost might not be installed
        with runner.isolated_filesystem():
            os.makedirs("infra")

            result = runner.invoke(cli, ["cost", "infra"])

            # Either works or warns about infracost
            assert result.exit_code == 0 or "Infracost" in result.output
