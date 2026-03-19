"""Tests for TerraGen modifier."""

import os
import json
import tempfile
import subprocess
import pytest
from pathlib import Path
from terragen.modifier import (
    read_terraform_files,
    read_state_file,
    get_git_info,
    summarize_state,
)


class TestReadTerraformFiles:
    """Test reading Terraform files."""

    def test_reads_tf_files(self):
        """Should read all .tf files in directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "main.tf")).write_text("resource {}")
            Path(os.path.join(tmpdir, "vars.tf")).write_text("variable {}")

            result = read_terraform_files(Path(tmpdir))

            assert "main.tf" in result
            assert "vars.tf" in result
            assert result["main.tf"] == "resource {}"

    def test_ignores_terraform_directory(self):
        """Should skip .terraform directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "main.tf")).write_text("resource {}")
            tf_dir = Path(os.path.join(tmpdir, ".terraform", "modules"))
            tf_dir.mkdir(parents=True)
            Path(os.path.join(tf_dir, "module.tf")).write_text("module {}")

            result = read_terraform_files(Path(tmpdir))

            assert "main.tf" in result
            assert not any(".terraform" in k for k in result.keys())

    def test_empty_directory(self):
        """Should return empty dict for directory with no .tf files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = read_terraform_files(Path(tmpdir))

            assert result == {}

    def test_nested_tf_files(self):
        """Should find nested .tf files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            modules_dir = Path(os.path.join(tmpdir, "modules", "vpc"))
            modules_dir.mkdir(parents=True)
            Path(os.path.join(modules_dir, "main.tf")).write_text("vpc {}")

            result = read_terraform_files(Path(tmpdir))

            assert any("vpc" in k for k in result.keys())


class TestReadStateFile:
    """Test reading Terraform state files."""

    def test_reads_local_state(self):
        """Should read local terraform.tfstate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {"version": 4, "resources": [{"type": "aws_s3_bucket"}]}
            Path(os.path.join(tmpdir, "terraform.tfstate")).write_text(
                json.dumps(state)
            )

            result = read_state_file(Path(tmpdir))

            assert result is not None
            assert result["version"] == 4
            assert len(result["resources"]) == 1

    def test_no_state_file(self):
        """Should return None when no state file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = read_state_file(Path(tmpdir))

            assert result is None

    def test_invalid_json_state(self):
        """Should handle invalid JSON in state file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "terraform.tfstate")).write_text("not valid json")

            result = read_state_file(Path(tmpdir))

            assert result is None


class TestGetGitInfo:
    """Test git repository detection."""

    def test_detects_git_repo(self):
        """Should detect git repository."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=tmpdir,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True
            )
            Path(os.path.join(tmpdir, "test.txt")).write_text("test")
            subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True
            )

            result = get_git_info(Path(tmpdir))

            assert result["is_repo"] is True
            assert result["branch"] is not None

    def test_non_git_directory(self):
        """Should return is_repo=False for non-git directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_git_info(Path(tmpdir))

            assert result["is_repo"] is False
            assert result["branch"] is None

    def test_detects_uncommitted_changes(self):
        """Should detect uncommitted changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=tmpdir,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True
            )
            Path(os.path.join(tmpdir, "test.txt")).write_text("test")
            subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True
            )
            # Add uncommitted change
            Path(os.path.join(tmpdir, "new.txt")).write_text("new")

            result = get_git_info(Path(tmpdir))

            assert result["uncommitted_changes"] is True


class TestSummarizeState:
    """Test state summarization."""

    def test_summarizes_resources(self):
        """Should summarize resources by type."""
        state = {
            "resources": [
                {"type": "aws_s3_bucket", "name": "bucket1"},
                {"type": "aws_s3_bucket", "name": "bucket2"},
                {"type": "aws_ec2_instance", "name": "server"},
            ]
        }

        result = summarize_state(state)

        assert "Total resources: 3" in result
        assert "aws_s3_bucket" in result
        assert "aws_ec2_instance" in result

    def test_empty_state(self):
        """Should handle empty state."""
        state = {"resources": []}

        result = summarize_state(state)

        assert "No resources" in result

    def test_none_state(self):
        """Should handle None state."""
        result = summarize_state(None)

        assert "No state file" in result

    def test_limits_resource_list(self):
        """Should limit displayed resources."""
        state = {
            "resources": [
                {"type": f"aws_resource_{i}", "name": f"res{i}"} for i in range(20)
            ]
        }

        result = summarize_state(state)

        assert "and" in result and "more" in result
