"""Integration tests for ConfigHole configuration management"""

import pytest

from confighole.utils.config import (
    get_global_daemon_settings,
    load_yaml_config,
    merge_global_settings,
    resolve_password,
    validate_instance_config,
)
from confighole.utils.exceptions import ConfigurationError

from .constants import PIHOLE_BASE_URL, PIHOLE_TEST_PASSWORD, TEST_CONFIG_PATH


@pytest.mark.integration
class TestConfigIntegration:
    """Integration tests for configuration management."""

    def test_load_yaml_config(self):
        """Test loading YAML configuration file."""
        config = load_yaml_config(TEST_CONFIG_PATH)

        assert isinstance(config, dict)
        assert "global" in config
        assert "instances" in config

        # Verify global settings
        global_settings = config["global"]
        assert global_settings["timeout"] == 30
        assert global_settings["verify_ssl"] is False
        assert global_settings["daemon_mode"] is False

        # Verify instances
        instances = config["instances"]
        assert len(instances) == 1
        assert instances[0]["name"] == "test-instance"

    def test_merge_global_settings(self):
        """Test merging global settings into instances."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        merged_instances = merge_global_settings(config)

        assert len(merged_instances) == 1
        instance = merged_instances[0]

        # Should have instance-specific settings
        assert instance["name"] == "test-instance"
        assert instance["base_url"] == PIHOLE_BASE_URL
        assert instance["password"] == PIHOLE_TEST_PASSWORD

        # Should have inherited global settings
        assert instance["timeout"] == 30
        assert instance["verify_ssl"] is False

        # Should NOT have daemon-specific settings
        assert "daemon_mode" not in instance
        assert "daemon_interval" not in instance

    def test_get_global_daemon_settings(self):
        """Test extracting daemon-specific settings."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        daemon_settings = get_global_daemon_settings(config)

        assert daemon_settings["daemon_mode"] is False
        assert daemon_settings["daemon_interval"] == 300
        assert daemon_settings["verbosity"] == 1
        assert daemon_settings["dry_run"] is False

    def test_resolve_password_direct(self):
        """Test resolving direct password."""
        instance_config = {"password": PIHOLE_TEST_PASSWORD}
        password = resolve_password(instance_config)
        assert password == PIHOLE_TEST_PASSWORD

    def test_validate_instance_config_valid(self):
        """Test validating valid instance configuration."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        merged_instances = merge_global_settings(config)
        instance = merged_instances[0]

        # Should not raise an exception
        validate_instance_config(instance)

    def test_validate_instance_config_missing_url(self):
        """Test validating instance with missing base_url."""
        instance_config = {"name": "test", "password": "test"}

        with pytest.raises(ConfigurationError, match="missing required 'base_url'"):
            validate_instance_config(instance_config)

    def test_validate_instance_config_missing_password(self):
        """Test validating instance with missing password."""
        instance_config = {"name": "test", "base_url": "http://test"}

        with pytest.raises(ConfigurationError, match="has no password configured"):
            validate_instance_config(instance_config)
