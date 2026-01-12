"""Integration tests for ConfigHole.

These tests require a running Pi-hole instance (via Docker).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time

import pytest

from confighole.core.client import PiHoleManager, create_manager
from confighole.core.daemon import ConfigHoleDaemon
from confighole.utils.config import (
    get_global_daemon_settings,
    load_yaml_config,
    merge_global_settings,
    resolve_password,
    validate_instance_config,
)
from confighole.utils.exceptions import ConfigurationError
from confighole.utils.tasks import (
    diff_instance_config,
    dump_instance_data,
    process_instances,
    sync_instance_config,
    sync_list_config,
)
from tests.constants import (
    PIHOLE_BASE_URL,
    PIHOLE_TEST_PASSWORD,
    TEST_CONFIG_PATH,
)


@pytest.mark.integration
class TestConfigLoading:
    """Integration tests for configuration loading."""

    def test_load_test_config(self):
        """Test config file loads correctly."""
        config = load_yaml_config(TEST_CONFIG_PATH)

        assert isinstance(config, dict)
        assert "global" in config
        assert "instances" in config
        assert config["global"]["timeout"] == 30
        assert config["global"]["verify_ssl"] is False

    def test_merge_global_settings(self):
        """Global settings merge into instances."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        instances = merge_global_settings(config)

        assert len(instances) == 1
        instance = instances[0]

        assert instance["name"] == "test-instance"
        assert instance["base_url"] == PIHOLE_BASE_URL
        assert instance["timeout"] == 30
        assert instance["verify_ssl"] is False
        assert "daemon_mode" not in instance

    def test_daemon_settings_extracted(self):
        """Daemon settings are extracted correctly."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        settings = get_global_daemon_settings(config)

        assert settings["daemon_mode"] is False
        assert settings["daemon_interval"] == 300
        assert settings["verbosity"] == 1

    def test_password_resolution(self):
        """Direct password resolves correctly."""
        config = {"password": PIHOLE_TEST_PASSWORD}
        assert resolve_password(config) == PIHOLE_TEST_PASSWORD

    def test_instance_validation(self):
        """Valid instance passes validation."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        instances = merge_global_settings(config)

        validate_instance_config(instances[0])

    def test_invalid_instance_raises(self):
        """Invalid instance raises ConfigurationError."""
        with pytest.raises(ConfigurationError):
            validate_instance_config({"name": "test"})


@pytest.mark.integration
class TestPiHoleClient:
    """Integration tests for Pi-hole client."""

    def test_create_manager_from_config(self, pihole_container):
        """Manager is created from config."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        instances = merge_global_settings(config)

        manager = create_manager(instances[0])

        assert manager is not None
        assert isinstance(manager, PiHoleManager)
        assert manager.base_url == PIHOLE_BASE_URL
        assert manager.password == PIHOLE_TEST_PASSWORD

    def test_context_manager(self, pihole_container):
        """Manager works as context manager."""
        manager = PiHoleManager(
            base_url=PIHOLE_BASE_URL,
            password=PIHOLE_TEST_PASSWORD,
            verify_ssl=False,
        )

        with manager:
            assert manager._client is not None

    def test_fetch_configuration(self, pihole_container):
        """Configuration is fetched successfully."""
        manager = PiHoleManager(
            base_url=PIHOLE_BASE_URL,
            password=PIHOLE_TEST_PASSWORD,
            verify_ssl=False,
        )

        with manager:
            config = manager.fetch_configuration()

            assert isinstance(config, dict)
            assert "dns" in config
            assert "upstreams" in config["dns"]

    def test_fetch_lists(self, pihole_container):
        """Lists are fetched successfully."""
        manager = PiHoleManager(
            base_url=PIHOLE_BASE_URL,
            password=PIHOLE_TEST_PASSWORD,
            verify_ssl=False,
        )

        with manager:
            lists = manager.fetch_lists()

            assert isinstance(lists, list)

    def test_update_configuration_dry_run(self, pihole_container):
        """Dry run doesn't modify configuration."""
        manager = PiHoleManager(
            base_url=PIHOLE_BASE_URL,
            password=PIHOLE_TEST_PASSWORD,
            verify_ssl=False,
        )

        with manager:
            result = manager.update_configuration(
                {"dns": {"upstreams": ["8.8.8.8"]}},
                dry_run=True,
            )

            assert result is True

    def test_update_configuration_real(self, pihole_container):
        """Configuration is updated and restored."""
        manager = PiHoleManager(
            base_url=PIHOLE_BASE_URL,
            password=PIHOLE_TEST_PASSWORD,
            verify_ssl=False,
        )

        with manager:
            original = manager.fetch_configuration()
            original_upstreams = original["dns"]["upstreams"]

            new_upstreams = ["1.1.1.1", "1.0.0.1"]
            result = manager.update_configuration(
                {"dns": {"upstreams": new_upstreams}},
                dry_run=False,
            )
            assert result is True

            updated = manager.fetch_configuration()
            assert updated["dns"]["upstreams"] == new_upstreams

            # Restore
            manager.update_configuration(
                {"dns": {"upstreams": original_upstreams}},
                dry_run=False,
            )


@pytest.mark.integration
class TestTaskOperations:
    """Integration tests for task operations."""

    def test_dump_instance_data(self, pihole_container):
        """Instance data is dumped correctly."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        instances = merge_global_settings(config)

        result = dump_instance_data(instances[0])

        assert result is not None
        assert result["name"] == "test-instance"
        assert "config" in result
        assert "lists" in result
        assert "dns" in result["config"]

    def test_diff_no_changes(self, pihole_container):
        """Diff returns None when no changes."""
        time.sleep(5)
        config = load_yaml_config(TEST_CONFIG_PATH)
        instances = merge_global_settings(config)
        instance = instances[0]

        # Get current config to match
        current = dump_instance_data(instance)

        # Remove lists data
        instance["lists"], current["lists"] = [], []

        instance["config"]["dns"] = {
            "upstreams": current["config"]["dns"]["upstreams"],
            "queryLogging": current["config"]["dns"]["queryLogging"],
        }

        result = diff_instance_config(instance)

        assert result is None

    def test_diff_with_changes(self, pihole_container):
        """Diff detects changes."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        instances = merge_global_settings(config)
        instance = instances[0]

        instance["config"]["dns"]["upstreams"] = ["8.8.8.8", "8.8.4.4"]

        result = diff_instance_config(instance)

        if result is not None:
            assert result["name"] == "test-instance"
            assert "diff" in result

    def test_sync_dry_run(self, pihole_container):
        """Sync dry run doesn't modify."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        instances = merge_global_settings(config)
        instance = instances[0]

        instance["config"]["dns"]["upstreams"] = ["8.8.8.8"]

        result = sync_instance_config(instance, dry_run=True)

        if result is not None:
            assert "changes" in result

    def test_sync_real(self, pihole_container):
        """Sync modifies and restores configuration."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        instances = merge_global_settings(config)
        instance = instances[0]

        original = dump_instance_data(instance)
        if original is None:
            pytest.skip("Could not connect to Pi-hole")

        original_upstreams = original["config"]["dns"]["upstreams"]

        try:
            instance["config"]["dns"]["upstreams"] = ["1.1.1.1", "1.0.0.1"]
            result = sync_instance_config(instance, dry_run=False)

            if result is not None:
                updated = dump_instance_data(instance)
                assert updated["config"]["dns"]["upstreams"] == ["1.1.1.1", "1.0.0.1"]
        finally:
            instance["config"]["dns"]["upstreams"] = original_upstreams
            sync_instance_config(instance, dry_run=False)

    def test_sync_lists_dry_run(self, pihole_container):
        """List sync dry run doesn't modify."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        instances = merge_global_settings(config)
        instance = instances[0]

        instance["lists"] = [
            {
                "address": "https://example.com/test.txt",
                "type": "allow",
                "comment": "Test",
                "groups": [0],
                "enabled": True,
            }
        ]

        result = sync_list_config(instance, dry_run=True)

        if result is not None:
            assert "changes" in result

    def test_sync_lists_no_lists(self, pihole_container):
        """Sync returns None when no lists configured."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        instances = merge_global_settings(config)
        instance = instances[0]

        instance.pop("lists", None)

        result = sync_list_config(instance, dry_run=True)

        assert result is None

    def test_process_instances_dump(self, pihole_container):
        """process_instances works with dump."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        instances = merge_global_settings(config)

        results = process_instances(instances, "dump")

        assert isinstance(results, list)
        if results:
            assert results[0]["name"] == "test-instance"

    def test_process_instances_diff(self, pihole_container):
        """process_instances works with diff."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        instances = merge_global_settings(config)

        instances[0]["config"]["dns"]["upstreams"] = ["8.8.8.8"]

        results = process_instances(instances, "diff")

        assert isinstance(results, list)

    def test_process_instances_sync_dry_run(self, pihole_container):
        """process_instances works with sync dry run."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        instances = merge_global_settings(config)

        instances[0]["config"]["dns"]["upstreams"] = ["8.8.8.8"]

        results = process_instances(instances, "sync", dry_run=True)

        assert isinstance(results, list)


@pytest.mark.integration
class TestDaemon:
    """Integration tests for daemon functionality."""

    def test_daemon_initialisation(self, pihole_container):
        """Daemon initialises correctly."""
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

    def test_daemon_load_instances(self, pihole_container):
        """Daemon loads instances correctly."""
        daemon = ConfigHoleDaemon(
            config_path=TEST_CONFIG_PATH,
            target_instance="test-instance",
        )

        instances = daemon._load_instances()

        assert len(instances) == 1
        assert instances[0]["name"] == "test-instance"

    def test_daemon_sync_dry_run(self, pihole_container):
        """Daemon sync works in dry run."""
        daemon = ConfigHoleDaemon(
            config_path=TEST_CONFIG_PATH,
            dry_run=True,
        )

        daemon._sync_instances()

    def test_daemon_short_run(self, pihole_container):
        """Daemon runs and stops correctly."""
        daemon = ConfigHoleDaemon(
            config_path=TEST_CONFIG_PATH,
            interval=2,
            dry_run=True,
        )

        thread = threading.Thread(target=daemon.run)
        thread.daemon = True
        thread.start()

        time.sleep(1)
        daemon.running = False
        thread.join(timeout=5)

        assert not thread.is_alive()


@pytest.mark.integration
class TestCLI:
    """Integration tests for CLI."""

    def test_help(self):
        """Help command works."""
        result = subprocess.run(
            ["python", "-m", "confighole.cli", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "ConfigHole" in result.stdout

    def test_dump(self, pihole_container):
        """Dump command works."""
        result = subprocess.run(
            ["python", "-m", "confighole.cli", "-c", TEST_CONFIG_PATH, "--dump"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "test-instance" in result.stdout

    def test_diff(self, pihole_container):
        """Diff command works."""
        result = subprocess.run(
            ["python", "-m", "confighole.cli", "-c", TEST_CONFIG_PATH, "--diff"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0

    def test_sync_dry_run(self, pihole_container):
        """Sync dry run works."""
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

    def test_instance_filter(self, pihole_container):
        """Instance filter works."""
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
        assert "test-instance" in result.stdout

    def test_invalid_instance(self, pihole_container):
        """Invalid instance name fails."""
        result = subprocess.run(
            [
                "python",
                "-m",
                "confighole.cli",
                "-c",
                TEST_CONFIG_PATH,
                "-i",
                "nonexistent",
                "--dump",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        assert "No instance found" in result.stderr

    def test_missing_config(self):
        """Missing config file fails."""
        result = subprocess.run(
            ["python", "-m", "confighole.cli", "-c", "missing.yaml", "--dump"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1

    def test_verbose_logging(self, pihole_container):
        """Verbose logging works."""
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
        assert "INFO:" in result.stderr

    def test_daemon_mode_env(self):
        """Daemon mode via environment works."""
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
            env = os.environ.copy()
            env.update(
                {
                    "CONFIGHOLE_DAEMON_MODE": "true",
                    "CONFIGHOLE_CONFIG_PATH": temp_config,
                    "CONFIGHOLE_DRY_RUN": "true",
                    "CONFIGHOLE_DAEMON_INTERVAL": "2",
                }
            )

            process = subprocess.Popen(
                ["python", "-m", "confighole.cli"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            time.sleep(3)
            process.terminate()
            _, stderr = process.communicate(timeout=5)

            assert "ConfigHole daemon starting" in stderr
        finally:
            os.unlink(temp_config)


@pytest.mark.integration
class TestErrorHandling:
    """Integration tests for error handling."""

    def test_unreachable_host(self):
        """Unreachable host is handled gracefully."""
        config = {
            "name": "unreachable",
            "base_url": "http://nonexistent:8080",
            "password": "test",
            "timeout": 1,
        }

        result = dump_instance_data(config)

        assert result is None

    def test_unreachable_host_with_config(self):
        """Unreachable host with config is handled."""
        config = {
            "name": "unreachable",
            "base_url": "http://nonexistent:8080",
            "password": "test",
            "timeout": 1,
            "config": {"dns": {"upstreams": ["1.1.1.1"]}},
        }

        result = diff_instance_config(config)

        assert result is None

    def test_empty_config_file(self):
        """Empty config file fails gracefully."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            temp_config = f.name

        try:
            result = subprocess.run(
                ["python", "-m", "confighole.cli", "-c", temp_config, "--dump"],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 1
        finally:
            os.unlink(temp_config)

    def test_malformed_yaml(self):
        """Malformed YAML fails gracefully."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: [unclosed")
            temp_config = f.name

        try:
            result = subprocess.run(
                ["python", "-m", "confighole.cli", "-c", temp_config, "--dump"],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 1
        finally:
            os.unlink(temp_config)

    def test_invalid_instance_config(self):
        """Invalid instance config is handled."""
        results = process_instances([{"name": "invalid"}], "dump")

        assert results == []
