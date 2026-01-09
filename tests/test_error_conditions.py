"""Tests for error conditions and edge cases"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from confighole.core.client import PiHoleManager, create_manager


@pytest.mark.unit
class TestErrorConditions:
    """Test error conditions and edge cases."""

    def test_dump_without_pihole_connection(self):
        """Test dump operation when Pi-hole is not accessible."""
        from confighole.utils.tasks import dump_instance_data

        # Create a config that will fail to connect
        instance_config = {
            "name": "unreachable",
            "base_url": "http://nonexistent:8080",
            "password": "test",
            "timeout": 1,  # Very short timeout
        }

        result = dump_instance_data(instance_config)

        # Should return None when connection fails
        assert result is None

    def test_diff_without_pihole_connection(self):
        """Test diff operation when Pi-hole is not accessible."""
        from confighole.utils.tasks import diff_instance_config

        instance_config = {
            "name": "unreachable",
            "base_url": "http://nonexistent:8080",
            "password": "test",
            "timeout": 1,
            "config": {"dns": {"upstreams": ["1.1.1.1"]}},
        }

        result = diff_instance_config(instance_config)

        # Should return None when connection fails
        assert result is None

    def test_sync_without_pihole_connection(self):
        """Test sync operation when Pi-hole is not accessible."""
        from confighole.utils.tasks import sync_instance_config

        instance_config = {
            "name": "unreachable",
            "base_url": "http://nonexistent:8080",
            "password": "test",
            "timeout": 1,
            "config": {"dns": {"upstreams": ["1.1.1.1"]}},
        }

        result = sync_instance_config(instance_config)

        # Should return None when connection fails
        assert result is None

    def test_pihole_manager_update_no_changes(self):
        """Test PiHoleManager update with no changes."""
        manager = PiHoleManager("http://test", "password")

        # Mock the client to avoid actual connection
        manager._client = Mock()

        result = manager.update_configuration({})

        # Should return True for empty changes
        assert result is True

    def test_pihole_manager_update_not_initialised(self):
        """Test PiHoleManager update when not initialised."""
        manager = PiHoleManager("http://test", "password")

        with pytest.raises(RuntimeError, match="Client not initialised"):
            manager.update_configuration({"dns": {"upstreams": ["1.1.1.1"]}})

    def test_pihole_manager_fetch_not_initialised(self):
        """Test PiHoleManager fetch when not initialised."""
        manager = PiHoleManager("http://test", "password")

        with pytest.raises(RuntimeError, match="Client not initialised"):
            manager.fetch_configuration()

    @patch("confighole.core.client.PiHoleClient")
    def test_pihole_manager_update_failure(self, mock_client_class):
        """Test PiHoleManager update when API call fails."""
        mock_client = Mock()
        mock_client.config.update_config.side_effect = Exception("API Error")
        mock_client_class.return_value = mock_client

        manager = PiHoleManager("http://test", "password")
        manager._client = mock_client

        result = manager.update_configuration({"dns": {"upstreams": ["1.1.1.1"]}})

        # Should return False when update fails
        assert result is False

    def test_create_manager_with_env_password(self):
        """Test creating manager with environment variable password."""
        os.environ["TEST_PIHOLE_PASSWORD"] = "secret123"

        try:
            instance_config = {
                "name": "test",
                "base_url": "http://test",
                "password": "${TEST_PIHOLE_PASSWORD}",
            }

            manager = create_manager(instance_config)

            assert manager is not None
            assert manager.password == "secret123"

        finally:
            del os.environ["TEST_PIHOLE_PASSWORD"]

    def test_create_manager_with_missing_env_password(self):
        """Test creating manager with missing environment variable password."""
        instance_config = {
            "name": "test",
            "base_url": "http://test",
            "password": "${MISSING_PASSWORD}",
        }

        manager = create_manager(instance_config)

        # Should return None when password resolution fails
        assert manager is None

    def test_daemon_config_from_env_invalid_values(self):
        """Test daemon config with invalid environment values."""
        from confighole.core.daemon import get_daemon_config_from_env

        # Set invalid values
        os.environ["CONFIGHOLE_DAEMON_MODE"] = "invalid"
        os.environ["CONFIGHOLE_DRY_RUN"] = "maybe"

        try:
            config = get_daemon_config_from_env()

            # Should use defaults for invalid values
            assert config["enabled"] is False  # Invalid boolean becomes False
            assert config["dry_run"] is False  # Invalid boolean becomes False

        finally:
            # Clean up
            for var in ["CONFIGHOLE_DAEMON_MODE", "CONFIGHOLE_DRY_RUN"]:
                if var in os.environ:
                    del os.environ[var]

    def test_daemon_config_from_env_invalid_interval(self):
        """Test daemon config with invalid interval value."""
        from confighole.core.daemon import get_daemon_config_from_env

        os.environ["CONFIGHOLE_DAEMON_INTERVAL"] = "not_a_number"

        try:
            # This should raise ValueError due to invalid int conversion
            with pytest.raises(ValueError):
                get_daemon_config_from_env()

        finally:
            if "CONFIGHOLE_DAEMON_INTERVAL" in os.environ:
                del os.environ["CONFIGHOLE_DAEMON_INTERVAL"]

    def test_cli_with_empty_config_file(self):
        """Test CLI with empty config file."""
        import subprocess

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")  # Empty file
            temp_config = f.name

        try:
            result = subprocess.run(
                ["python", "-m", "confighole.cli", "-c", temp_config, "--dump"],
                capture_output=True,
                text=True,
            )

            # Should handle empty config gracefully
            assert result.returncode == 1

        finally:
            os.unlink(temp_config)

    def test_cli_with_malformed_yaml(self):
        """Test CLI with malformed YAML config."""
        import subprocess

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: [unclosed")
            temp_config = f.name

        try:
            result = subprocess.run(
                ["python", "-m", "confighole.cli", "-c", temp_config, "--dump"],
                capture_output=True,
                text=True,
            )

            # Should handle malformed YAML gracefully
            assert result.returncode == 1

        finally:
            os.unlink(temp_config)

    def test_process_instances_with_configuration_error(self):
        """Test processing instances when configuration validation fails."""
        from confighole.utils.tasks import process_instances

        # Instance with missing required fields
        instances = [{"name": "invalid"}]  # Missing base_url and password

        results = process_instances(instances, "dump")

        # Should handle configuration errors gracefully
        assert results == []

    @patch("confighole.utils.tasks.create_manager")
    def test_dump_instance_data_with_exception(self, mock_create_manager):
        """Test dump_instance_data when manager raises exception."""
        from confighole.utils.tasks import dump_instance_data

        # Mock manager that raises exception in context manager
        mock_manager = Mock()
        mock_manager.__enter__ = Mock(side_effect=Exception("Connection failed"))
        mock_manager.__exit__ = Mock(return_value=None)
        mock_create_manager.return_value = mock_manager

        instance_config = {
            "name": "test",
            "base_url": "http://test",
            "password": "test",
        }

        result = dump_instance_data(instance_config)

        # Should return None when exception occurs
        assert result is None

    def test_normalise_hosts_with_multiple_spaces(self):
        """Test normalising hosts with multiple spaces."""
        from confighole.utils.helpers import normalise_dns_hosts

        hosts = ["192.168.1.1   gateway.test"]  # Multiple spaces

        result = normalise_dns_hosts(hosts)

        expected = [{"ip": "192.168.1.1", "host": "gateway.test"}]
        assert result == expected

    def test_normalise_cnames_with_extra_whitespace(self):
        """Test normalising CNAMEs with extra whitespace."""
        from confighole.utils.helpers import normalise_cname_records

        cnames = [" plex.test , nas.test "]  # Extra whitespace

        result = normalise_cname_records(cnames)

        expected = [{"name": "plex.test", "target": "nas.test"}]
        assert result == expected

    def test_diff_calculation_with_empty_lists(self):
        """Test diff calculation with empty lists."""
        from confighole.utils.diff import calculate_config_diff

        local = {"dns": {"upstreams": []}}
        remote = {"dns": {"upstreams": ["1.1.1.1"]}}

        result = calculate_config_diff(local, remote)

        assert "dns.upstreams" in result
        assert result["dns.upstreams"]["local"] == []
        assert result["dns.upstreams"]["remote"] == ["1.1.1.1"]

    def test_diff_calculation_with_nested_empty_dicts(self):
        """Test diff calculation with nested empty dictionaries."""
        from confighole.utils.diff import calculate_config_diff

        local = {"dns": {"domain": {"name": "test"}}}
        remote = {"dns": {"domain": {}}}

        result = calculate_config_diff(local, remote)

        # Should detect the difference in nested structure
        assert "dns.domain.name" in result
