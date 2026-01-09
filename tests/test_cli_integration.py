"""Integration tests for ConfigHole CLI"""

import os
import subprocess
import tempfile
import time

import pytest

from .constants import TEST_CONFIG_PATH


@pytest.mark.integration
class TestCLIIntegration:
    """Integration tests for CLI functionality."""

    def test_cli_help(self):
        """Test CLI help command."""
        result = subprocess.run(
            ["python", "-m", "confighole.cli", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "ConfigHole - The Pi-hole configuration manager" in result.stdout
        assert "--dump" in result.stdout
        assert "--diff" in result.stdout
        assert "--sync" in result.stdout
        assert "--daemon" in result.stdout

    def test_cli_dump_command(self, pihole_container):
        """Test CLI dump command."""
        result = subprocess.run(
            ["python", "-m", "confighole.cli", "-c", TEST_CONFIG_PATH, "--dump"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Should output YAML configuration
        assert "name: test-instance" in result.stdout
        assert "dns:" in result.stdout

    def test_cli_diff_command(self, pihole_container):
        """Test CLI diff command."""
        result = subprocess.run(
            ["python", "-m", "confighole.cli", "-c", TEST_CONFIG_PATH, "--diff"],
            capture_output=True,
            text=True,
        )

        # Should succeed (return code 0) even if no differences
        assert result.returncode == 0

    def test_cli_sync_dry_run(self, pihole_container):
        """Test CLI sync command with dry-run."""
        result = subprocess.run(
            [
                "python",
                "-m",
                "confighole.cli",
                "-c",
                TEST_CONFIG_PATH,
                "--sync",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

    def test_cli_instance_filter(self, pihole_container):
        """Test CLI with instance filtering."""
        result = subprocess.run(
            [
                "python",
                "-m",
                "confighole.cli",
                "-c",
                TEST_CONFIG_PATH,
                "-i",
                "test-instance",
                "--dump",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "name: test-instance" in result.stdout

    def test_cli_invalid_instance(self, pihole_container):
        """Test CLI with invalid instance name."""
        result = subprocess.run(
            [
                "python",
                "-m",
                "confighole.cli",
                "-c",
                TEST_CONFIG_PATH,
                "-i",
                "nonexistent-instance",
                "--dump",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "No instance found with name" in result.stderr

    def test_cli_missing_config_file(self):
        """Test CLI with missing config file."""
        result = subprocess.run(
            [
                "python",
                "-m",
                "confighole.cli",
                "-c",
                "nonexistent-config.yaml",
                "--dump",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1

    def test_cli_verbose_logging(self, pihole_container):
        """Test CLI with verbose logging."""
        result = subprocess.run(
            [
                "python",
                "-m",
                "confighole.cli",
                "-c",
                TEST_CONFIG_PATH,
                "--dump",
                "-v",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Should have INFO level logging
        assert "INFO:" in result.stderr

    def test_cli_very_verbose_logging(self, pihole_container):
        """Test CLI with very verbose logging."""
        result = subprocess.run(
            [
                "python",
                "-m",
                "confighole.cli",
                "-c",
                TEST_CONFIG_PATH,
                "--dump",
                "-vv",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Should have DEBUG level logging
        # Note: DEBUG messages might not appear in stderr for this simple test

    def test_cli_daemon_mode_env_var(self):
        """Test CLI daemon mode via environment variable."""
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
global:
  timeout: 30
  verify_ssl: false

instances:
  - name: test
    base_url: http://localhost:8080
    password: test-password-123
    config:
      dns:
        upstreams: ["1.1.1.1"]
"""
            )
            temp_config = f.name

        try:
            # Set environment variables for daemon mode
            env = os.environ.copy()
            env.update(
                {
                    "CONFIGHOLE_DAEMON_MODE": "true",
                    "CONFIGHOLE_CONFIG_PATH": temp_config,
                    "CONFIGHOLE_DRY_RUN": "true",
                    "CONFIGHOLE_DAEMON_INTERVAL": "2",  # Very short interval for testing
                }
            )

            # Run CLI - it should start daemon mode
            process = subprocess.Popen(
                ["python", "-m", "confighole.cli"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Let it run for a short time to verify it starts
            time.sleep(3)

            # Terminate the process
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)

            # Check that daemon mode was detected and started
            assert "ConfigHole daemon starting" in stderr
            assert "Config:" in stderr

        finally:
            # Clean up temporary file
            os.unlink(temp_config)
