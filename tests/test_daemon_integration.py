"""Integration tests for ConfigHole daemon"""

import os
import threading
import time

import pytest

from confighole.core.daemon import (
    ConfigHoleDaemon,
    get_daemon_config_from_env,
    run_daemon_from_env,
)

from .constants import TEST_CONFIG_PATH


@pytest.mark.integration
class TestDaemonIntegration:
    """Integration tests for daemon functionality."""

    def test_get_daemon_config_from_env_defaults(self):
        """Test getting daemon config with default values."""
        # Clear environment variables
        env_vars = [
            "CONFIGHOLE_DAEMON_MODE",
            "CONFIGHOLE_DAEMON_INTERVAL",
            "CONFIGHOLE_CONFIG_PATH",
            "CONFIGHOLE_INSTANCE",
            "CONFIGHOLE_DRY_RUN",
        ]

        original_values = {}
        for var in env_vars:
            original_values[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]

        try:
            config = get_daemon_config_from_env()

            assert config["enabled"] is False
            assert config["interval"] == 300
            assert config["config_path"] is None
            assert config["instance"] is None
            assert config["dry_run"] is False

        finally:
            # Restore original environment
            for var, value in original_values.items():
                if value is not None:
                    os.environ[var] = value

    def test_get_daemon_config_from_env_set(self):
        """Test getting daemon config with environment variables set."""
        env_vars = {
            "CONFIGHOLE_DAEMON_MODE": "true",
            "CONFIGHOLE_DAEMON_INTERVAL": "600",
            "CONFIGHOLE_CONFIG_PATH": "/test/config.yaml",
            "CONFIGHOLE_INSTANCE": "test-instance",
            "CONFIGHOLE_DRY_RUN": "true",
        }

        # Set environment variables
        original_values = {}
        for var, value in env_vars.items():
            original_values[var] = os.environ.get(var)
            os.environ[var] = value

        try:
            config = get_daemon_config_from_env()

            assert config["enabled"] is True
            assert config["interval"] == 600
            assert config["config_path"] == "/test/config.yaml"
            assert config["instance"] == "test-instance"
            assert config["dry_run"] is True

        finally:
            # Restore original environment
            for var, value in original_values.items():
                if value is not None:
                    os.environ[var] = value
                elif var in os.environ:
                    del os.environ[var]

    def test_daemon_initialisation(self, pihole_container):
        """Test daemon initialisation."""
        daemon = ConfigHoleDaemon(
            config_path=TEST_CONFIG_PATH,
            interval=60,
            target_instance="test-instance",
            dry_run=True,
        )

        assert daemon.config_path == TEST_CONFIG_PATH
        assert daemon.interval == 60
        assert daemon.target_instance == "test-instance"
        assert daemon.dry_run is True
        assert daemon.running is False

    def test_daemon_load_instances(self, pihole_container):
        """Test daemon loading instances from config."""
        daemon = ConfigHoleDaemon(
            config_path=TEST_CONFIG_PATH,
            target_instance="test-instance",
        )

        instances = daemon._load_instances()

        assert isinstance(instances, list)
        assert len(instances) == 1
        assert instances[0]["name"] == "test-instance"

    def test_daemon_load_instances_all(self, pihole_container):
        """Test daemon loading all instances when no target specified."""
        daemon = ConfigHoleDaemon(config_path=TEST_CONFIG_PATH)

        instances = daemon._load_instances()

        assert isinstance(instances, list)
        assert len(instances) == 1  # Our test config has one instance

    def test_daemon_sync_instances_dry_run(self, pihole_container):
        """Test daemon sync in dry-run mode."""
        daemon = ConfigHoleDaemon(
            config_path=TEST_CONFIG_PATH,
            dry_run=True,
        )

        # This should not raise an exception
        daemon._sync_instances()

    def test_daemon_short_run(self, pihole_container):
        """Test daemon running for a short period."""
        daemon = ConfigHoleDaemon(
            config_path=TEST_CONFIG_PATH,
            interval=2,  # Very short interval for testing
            dry_run=True,
        )

        # Run daemon in a separate thread
        daemon_thread = threading.Thread(target=daemon.run)
        daemon_thread.daemon = True
        daemon_thread.start()

        # Let it run for a short time
        time.sleep(1)

        # Stop the daemon
        daemon.running = False
        daemon_thread.join(timeout=5)

        # Thread should have finished
        assert not daemon_thread.is_alive()

    def test_run_daemon_from_env_missing_config(self):
        """Test running daemon from env with missing config path."""
        # Set environment to enable daemon but no config path
        original_values = {}
        env_vars = {
            "CONFIGHOLE_DAEMON_MODE": "true",
            "CONFIGHOLE_CONFIG_PATH": "",
        }

        for var, value in env_vars.items():
            original_values[var] = os.environ.get(var)
            os.environ[var] = value

        try:
            with pytest.raises(SystemExit):
                run_daemon_from_env()

        finally:
            # Restore original environment
            for var, value in original_values.items():
                if value is not None:
                    os.environ[var] = value
                elif var in os.environ:
                    del os.environ[var]

    def test_run_daemon_from_env_disabled(self):
        """Test running daemon from env when disabled."""
        # Set environment to disable daemon
        original_value = os.environ.get("CONFIGHOLE_DAEMON_MODE")
        os.environ["CONFIGHOLE_DAEMON_MODE"] = "false"

        try:
            with pytest.raises(SystemExit):
                run_daemon_from_env()

        finally:
            # Restore original environment
            if original_value is not None:
                os.environ["CONFIGHOLE_DAEMON_MODE"] = original_value
            elif "CONFIGHOLE_DAEMON_MODE" in os.environ:
                del os.environ["CONFIGHOLE_DAEMON_MODE"]
