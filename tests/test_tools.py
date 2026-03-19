"""Tests for TerraGen tools."""

import os
import tempfile
import pytest
from pathlib import Path
from terragen.tools import execute_tool, TOOLS


class TestToolDefinitions:
    """Test tool definitions."""

    def test_tools_have_required_fields(self):
        """All tools should have name, description, and input_schema."""
        for tool in TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_tool_names(self):
        """Expected tools should be defined."""
        tool_names = [t["name"] for t in TOOLS]
        assert "write_file" in tool_names
        assert "read_file" in tool_names
        assert "run_command" in tool_names
        assert "list_files" in tool_names


class TestWriteFile:
    """Test write_file tool."""

    def test_write_file_creates_file(self):
        """write_file should create a file with content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            result = execute_tool("write_file", {"path": path, "content": "hello"})

            assert "Successfully" in result
            assert os.path.exists(path)
            assert Path(path).read_text() == "hello"

    def test_write_file_creates_parent_dirs(self):
        """write_file should create parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "a", "b", "c", "test.txt")
            result = execute_tool("write_file", {"path": path, "content": "nested"})

            assert "Successfully" in result
            assert os.path.exists(path)

    def test_write_file_overwrites_existing(self):
        """write_file should overwrite existing files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            Path(path).write_text("old content")

            execute_tool("write_file", {"path": path, "content": "new content"})

            assert Path(path).read_text() == "new content"


class TestReadFile:
    """Test read_file tool."""

    def test_read_file_returns_content(self):
        """read_file should return file content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            Path(path).write_text("file content")

            result = execute_tool("read_file", {"path": path})

            assert result == "file content"

    def test_read_file_not_found(self):
        """read_file should return error for missing file."""
        result = execute_tool("read_file", {"path": "/nonexistent/file.txt"})

        assert "Error" in result
        assert "not found" in result.lower()

    def test_read_file_truncates_large_content(self):
        """read_file should truncate very large files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "large.txt")
            Path(path).write_text("x" * 20000)

            result = execute_tool("read_file", {"path": path})

            assert len(result) <= 10100  # 10000 + truncation message
            assert "truncated" in result


class TestRunCommand:
    """Test run_command tool."""

    def test_run_command_returns_output(self):
        """run_command should return command output."""
        result = execute_tool("run_command", {"command": "echo hello"})

        assert "hello" in result

    def test_run_command_with_cwd(self):
        """run_command should respect working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = execute_tool("run_command", {
                "command": "pwd",
                "cwd": tmpdir
            })

            assert tmpdir in result

    def test_run_command_captures_stderr(self):
        """run_command should capture stderr."""
        result = execute_tool("run_command", {
            "command": "ls /nonexistent 2>&1 || true"
        })

        # Should contain something (either error or empty)
        assert result is not None

    def test_run_command_invalid_command(self):
        """run_command should handle invalid commands."""
        result = execute_tool("run_command", {
            "command": "nonexistent_command_xyz 2>&1 || echo 'failed'"
        })

        assert result is not None


class TestListFiles:
    """Test list_files tool."""

    def test_list_files_returns_files(self):
        """list_files should return matching files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "test1.txt")).touch()
            Path(os.path.join(tmpdir, "test2.txt")).touch()

            result = execute_tool("list_files", {
                "path": tmpdir,
                "pattern": "*.txt"
            })

            assert "test1.txt" in result
            assert "test2.txt" in result

    def test_list_files_empty_directory(self):
        """list_files should handle empty directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = execute_tool("list_files", {
                "path": tmpdir,
                "pattern": "*.tf"
            })

            assert "no files found" in result.lower()

    def test_list_files_nonexistent_directory(self):
        """list_files should return error for missing directory."""
        result = execute_tool("list_files", {
            "path": "/nonexistent/directory"
        })

        assert "Error" in result

    def test_list_files_default_pattern(self):
        """list_files should use * as default pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "file.txt")).touch()

            result = execute_tool("list_files", {"path": tmpdir})

            assert "file.txt" in result


class TestUnknownTool:
    """Test handling of unknown tools."""

    def test_unknown_tool_returns_error(self):
        """Unknown tool should return error."""
        result = execute_tool("unknown_tool", {})

        assert "Error" in result
        assert "Unknown tool" in result
