"""Unit tests for ConfigHole utility functions"""

import os
import tempfile
from unittest.mock import patch

import pytest

from confighole.utils.config import (
    get_global_daemon_settings,
    load_yaml_config,
    merge_global_settings,
    resolve_password,
)
from confighole.utils.diff import calculate_config_diff, convert_diff_to_nested_dict
from confighole.utils.exceptions import ConfigurationError
from confighole.utils.helpers import (
    cnames_to_pihole_format,
    hosts_to_pihole_format,
    normalise_cname_records,
    normalise_dns_configuration,
    normalise_dns_hosts,
    validate_instance_config,
)

from .constants import TEST_DNS_CNAMES, TEST_DNS_HOSTS, TEST_DNS_UPSTREAMS


@pytest.mark.unit
class TestConfigUtils:
    """Unit tests for configuration utilities."""

    def test_merge_global_settings_empty(self):
        """Test merging with empty global settings."""
        config = {
            "global": {},
            "instances": [{"name": "test", "base_url": "http://test"}],
        }

        result = merge_global_settings(config)

        assert len(result) == 1
        assert result[0]["name"] == "test"
        assert result[0]["base_url"] == "http://test"

    def test_merge_global_settings_with_overrides(self):
        """Test merging with instance overrides."""
        config = {
            "global": {"timeout": 30, "verify_ssl": False},
            "instances": [
                {
                    "name": "test",
                    "base_url": "http://test",
                    "timeout": 60,  # Override global
                }
            ],
        }

        result = merge_global_settings(config)

        assert result[0]["timeout"] == 60  # Instance override
        assert result[0]["verify_ssl"] is False  # From global

    def test_get_global_daemon_settings_defaults(self):
        """Test getting daemon settings with defaults."""
        config = {"global": {}}

        result = get_global_daemon_settings(config)

        assert result["daemon_mode"] is False
        assert result["daemon_interval"] == 300
        assert result["verbosity"] == 1
        assert result["dry_run"] is False

    def test_resolve_password_env_var_syntax(self):
        """Test resolving password with ${VAR} syntax."""
        os.environ["TEST_PASSWORD"] = "secret123"

        try:
            instance_config = {"password": "${TEST_PASSWORD}"}
            result = resolve_password(instance_config)
            assert result == "secret123"
        finally:
            del os.environ["TEST_PASSWORD"]

    def test_resolve_password_env_var_missing(self):
        """Test resolving password with missing env var."""
        instance_config = {"password": "${NONEXISTENT_VAR}"}
        result = resolve_password(instance_config)
        assert result is None

    def test_resolve_password_password_env(self):
        """Test resolving password with password_env."""
        os.environ["MY_PASSWORD"] = "secret456"

        try:
            instance_config = {"password_env": "MY_PASSWORD"}
            result = resolve_password(instance_config)
            assert result == "secret456"
        finally:
            del os.environ["MY_PASSWORD"]


@pytest.mark.unit
class TestDiffUtils:
    """Unit tests for diff utilities."""

    def test_calculate_config_diff_no_changes(self):
        """Test diff calculation with no changes."""
        local = {"dns": {"upstreams": ["1.1.1.1"]}}
        remote = {"dns": {"upstreams": ["1.1.1.1"]}}

        result = calculate_config_diff(local, remote)

        assert result == {}

    def test_calculate_config_diff_with_changes(self):
        """Test diff calculation with changes."""
        local = {"dns": {"upstreams": ["1.1.1.1"]}}
        remote = {"dns": {"upstreams": ["8.8.8.8"]}}

        result = calculate_config_diff(local, remote)

        assert "dns.upstreams" in result
        assert result["dns.upstreams"]["local"] == ["1.1.1.1"]
        assert result["dns.upstreams"]["remote"] == ["8.8.8.8"]

    def test_calculate_config_diff_nested(self):
        """Test diff calculation with nested changes."""
        local = {"dns": {"domain": {"name": "test", "local": True}}}
        remote = {"dns": {"domain": {"name": "prod", "local": False}}}

        result = calculate_config_diff(local, remote)

        assert "dns.domain.name" in result
        assert "dns.domain.local" in result

    def test_convert_diff_to_nested_dict(self):
        """Test converting flat diff to nested dict."""
        diff = {
            "dns.upstreams": {"local": ["1.1.1.1"], "remote": ["8.8.8.8"]},
            "dns.queryLogging": {"local": True, "remote": False},
        }

        result = convert_diff_to_nested_dict(diff)

        assert "dns" in result
        assert result["dns"]["upstreams"] == ["1.1.1.1"]
        assert result["dns"]["queryLogging"] is True


@pytest.mark.unit
class TestHelperUtils:
    """Unit tests for helper utilities."""

    def test_normalise_dns_hosts_list_format(self):
        """Test normalising DNS hosts from list format."""
        hosts = [
            {"ip": "192.168.1.1", "host": "gateway.test"},
            {"ip": "192.168.1.10", "host": "nas.test"},
        ]

        result = normalise_dns_hosts(hosts)

        assert result == hosts  # Should be unchanged

    def test_normalise_dns_hosts_string_format(self):
        """Test normalising DNS hosts from string format."""
        hosts = ["192.168.1.1 gateway.test"]

        result = normalise_dns_hosts(hosts)

        expected = [{"ip": "192.168.1.1", "host": "gateway.test"}]
        assert result == expected

    def test_normalise_cname_records_list_format(self):
        """Test normalising CNAME records from list format."""
        cnames = [
            {"name": "plex.test", "target": "nas.test"},
            {"name": "grafana.test", "target": "gateway.test"},
        ]

        result = normalise_cname_records(cnames)

        assert result == cnames  # Should be unchanged

    def test_normalise_cname_records_string_format(self):
        """Test normalising CNAME records from string format."""
        cnames = ["plex.test,nas.test"]

        result = normalise_cname_records(cnames)

        expected = [{"name": "plex.test", "target": "nas.test"}]
        assert result == expected

    def test_normalise_dns_configuration(self):
        """Test normalising complete DNS configuration."""
        config = {
            "dns": {
                "upstreams": TEST_DNS_UPSTREAMS,
                "hosts": TEST_DNS_HOSTS,
                "cnameRecords": TEST_DNS_CNAMES,
            }
        }

        result = normalise_dns_configuration(config)

        assert "dns" in result
        dns = result["dns"]
        assert dns["upstreams"] == TEST_DNS_UPSTREAMS
        assert dns["hosts"] == TEST_DNS_HOSTS
        assert dns["cnameRecords"] == TEST_DNS_CNAMES

    def test_hosts_to_pihole_format(self):
        """Test converting hosts to Pi-hole format."""
        hosts = [
            {"ip": "192.168.1.1", "host": "gateway.test"},
            {"ip": "192.168.1.10", "host": "nas.test"},
        ]

        result = hosts_to_pihole_format(hosts)

        expected = ["192.168.1.1 gateway.test", "192.168.1.10 nas.test"]
        assert result == expected

    def test_cnames_to_pihole_format(self):
        """Test converting CNAMEs to Pi-hole format."""
        cnames = [
            {"name": "plex.test", "target": "nas.test"},
            {"name": "grafana.test", "target": "gateway.test"},
        ]

        result = cnames_to_pihole_format(cnames)

        expected = ["plex.test,nas.test", "grafana.test,gateway.test"]
        assert result == expected


# Additional unit tests for better coverage


@pytest.mark.unit
class TestConfigUtilsExtended:
    """Extended unit tests for configuration utilities."""

    def test_load_yaml_config_missing_file(self):
        """Test loading non-existent YAML file."""
        with pytest.raises(SystemExit):
            load_yaml_config("nonexistent.yaml")

    def test_load_yaml_config_invalid_yaml(self):
        """Test loading invalid YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_file = f.name

        try:
            with pytest.raises(SystemExit):  # Config loader calls sys.exit
                load_yaml_config(temp_file)
        finally:
            os.unlink(temp_file)

    def test_merge_global_settings_no_instances(self):
        """Test merging with no instances."""
        config = {"global": {"timeout": 30}, "instances": []}

        result = merge_global_settings(config)

        assert result == []

    def test_get_global_daemon_settings_no_global(self):
        """Test getting daemon settings with no global section."""
        config = {}

        result = get_global_daemon_settings(config)

        assert result["daemon_mode"] is False
        assert result["daemon_interval"] == 300
        assert result["verbosity"] == 1
        assert result["dry_run"] is False

    def test_resolve_password_password_env_missing(self):
        """Test resolving password with missing password_env."""
        instance_config = {"password_env": "NONEXISTENT_PASSWORD"}
        result = resolve_password(instance_config)
        assert result is None

    def test_resolve_password_no_password(self):
        """Test resolving password with no password configured."""
        instance_config = {"name": "test"}
        result = resolve_password(instance_config)
        assert result is None


@pytest.mark.unit
class TestValidationUtils:
    """Unit tests for validation utilities."""

    def test_validate_instance_config_valid(self):
        """Test validating valid instance configuration."""
        instance_config = {
            "name": "test",
            "base_url": "http://test",
            "password": "secret",
        }

        # Should not raise an exception
        validate_instance_config(instance_config)

    def test_validate_instance_config_missing_url(self):
        """Test validating instance with missing base_url."""
        instance_config = {"name": "test", "password": "test"}

        with pytest.raises(ConfigurationError, match="missing required 'base_url'"):
            validate_instance_config(instance_config)

    def test_validate_instance_config_empty_url(self):
        """Test validating instance with empty base_url."""
        instance_config = {"name": "test", "base_url": "", "password": "test"}

        with pytest.raises(ConfigurationError, match="missing required 'base_url'"):
            validate_instance_config(instance_config)

    def test_validate_instance_config_missing_password(self):
        """Test validating instance with missing password."""
        instance_config = {"name": "test", "base_url": "http://test"}

        with pytest.raises(ConfigurationError, match="has no password configured"):
            validate_instance_config(instance_config)


@pytest.mark.unit
class TestDiffUtilsExtended:
    """Extended unit tests for diff utilities."""

    def test_calculate_config_diff_type_mismatch(self):
        """Test diff calculation with type mismatches."""
        local = {"dns": {"upstreams": ["1.1.1.1"]}}
        remote = {"dns": {"upstreams": "1.1.1.1"}}  # String instead of list

        result = calculate_config_diff(local, remote)

        assert "dns.upstreams" in result

    def test_calculate_config_diff_none_remote(self):
        """Test diff calculation with None remote config."""
        local = {"dns": {"upstreams": ["1.1.1.1"]}}
        remote = None

        result = calculate_config_diff(local, remote)

        assert "dns.upstreams" in result

    def test_convert_diff_to_nested_dict_with_hosts(self):
        """Test converting diff with hosts to Pi-hole format."""
        diff = {
            "dns.hosts": {
                "local": [{"ip": "192.168.1.1", "host": "test.local"}],
                "remote": [],
            }
        }

        result = convert_diff_to_nested_dict(diff)

        assert result["dns"]["hosts"] == ["192.168.1.1 test.local"]

    def test_convert_diff_to_nested_dict_with_cnames(self):
        """Test converting diff with CNAMEs to Pi-hole format."""
        diff = {
            "dns.cnameRecords": {
                "local": [{"name": "test.local", "target": "server.local"}],
                "remote": [],
            }
        }

        result = convert_diff_to_nested_dict(diff)

        assert result["dns"]["cnameRecords"] == ["test.local,server.local"]


@pytest.mark.unit
class TestHelperUtilsExtended:
    """Extended unit tests for helper utilities."""

    def test_normalise_dns_hosts_invalid_dict(self):
        """Test normalising DNS hosts with invalid dict format."""
        hosts = [{"ip": "192.168.1.1"}]  # Missing 'host' key

        with pytest.raises(ConfigurationError):
            normalise_dns_hosts(hosts)

    def test_normalise_dns_hosts_invalid_format(self):
        """Test normalising DNS hosts with invalid format."""
        hosts = [123]  # Invalid type

        with pytest.raises(ConfigurationError):
            normalise_dns_hosts(hosts)

    def test_normalise_dns_hosts_string_no_space(self):
        """Test normalising DNS hosts with string without space."""
        hosts = ["192.168.1.1"]  # No space separator

        with pytest.raises(ConfigurationError):
            normalise_dns_hosts(hosts)

    def test_normalise_cname_records_invalid_dict(self):
        """Test normalising CNAME records with invalid dict format."""
        cnames = [{"name": "plex.test"}]  # Missing 'target' key

        with pytest.raises(ConfigurationError):
            normalise_cname_records(cnames)

    def test_normalise_cname_records_invalid_format(self):
        """Test normalising CNAME records with invalid format."""
        cnames = [123]  # Invalid type

        with pytest.raises(ConfigurationError):
            normalise_cname_records(cnames)

    def test_normalise_cname_records_string_no_comma(self):
        """Test normalising CNAME records with string without comma."""
        cnames = ["plex.test"]  # No comma separator

        with pytest.raises(ConfigurationError):
            normalise_cname_records(cnames)

    def test_normalise_dns_configuration_no_dns(self):
        """Test normalising configuration without DNS section."""
        config = {"other": "data"}

        result = normalise_dns_configuration(config)

        assert result == config

    def test_normalise_dns_configuration_invalid_dns(self):
        """Test normalising configuration with invalid DNS section."""
        config = {"dns": "not_a_dict"}

        result = normalise_dns_configuration(config)

        assert result == config


@pytest.mark.unit
class TestClientUtils:
    """Unit tests for client utilities."""

    def test_pihole_manager_init_no_password(self):
        """Test PiHoleManager initialisation with no password."""
        from confighole.core.client import PiHoleManager

        with pytest.raises(ValueError, match="Password cannot be None or empty"):
            PiHoleManager("http://test", "")

    def test_pihole_manager_init_none_password(self):
        """Test PiHoleManager initialisation with None password."""
        from confighole.core.client import PiHoleManager

        with pytest.raises(ValueError, match="Password cannot be None or empty"):
            PiHoleManager("http://test", None)

    def test_create_manager_invalid_config(self):
        """Test creating manager with invalid configuration."""
        from confighole.core.client import create_manager

        instance_config = {"name": "test"}  # Missing required fields

        result = create_manager(instance_config)

        assert result is None

    def test_create_manager_no_password(self):
        """Test creating manager with no password."""
        from confighole.core.client import create_manager

        instance_config = {"name": "test", "base_url": "http://test"}

        result = create_manager(instance_config)

        assert result is None


@pytest.mark.unit
class TestTasksUtils:
    """Unit tests for task utilities."""

    def test_process_instances_invalid_operation(self):
        """Test processing instances with invalid operation."""
        from confighole.utils.tasks import process_instances

        instances = [{"name": "test"}]

        with pytest.raises(ValueError, match="Unknown operation"):
            process_instances(instances, "invalid_operation")

    @patch("confighole.utils.tasks.create_manager")
    def test_dump_instance_data_no_manager(self, mock_create_manager):
        """Test dumping instance data when manager creation fails."""
        from confighole.utils.tasks import dump_instance_data

        mock_create_manager.return_value = None
        instance_config = {"name": "test", "base_url": "http://test"}

        result = dump_instance_data(instance_config)

        assert result is None

    @patch("confighole.utils.tasks.create_manager")
    def test_diff_instance_config_no_local_config(self, mock_create_manager):
        """Test diffing when no local config is present."""
        from confighole.utils.tasks import diff_instance_config

        instance_config = {"name": "test", "base_url": "http://test"}

        result = diff_instance_config(instance_config)

        assert result is None

    @patch("confighole.utils.tasks.create_manager")
    def test_sync_instance_config_no_local_config(self, mock_create_manager):
        """Test syncing when no local config is present."""
        from confighole.utils.tasks import sync_instance_config

        instance_config = {"name": "test", "base_url": "http://test"}

        result = sync_instance_config(instance_config)

        assert result is None


@pytest.mark.unit
class TestCLIErrorHandling:
    """Unit tests for CLI error handling."""

    def test_cli_missing_config_file(self):
        """Test CLI with missing config file."""
        import subprocess

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

    def test_cli_invalid_instance_name(self):
        """Test CLI with invalid instance name."""
        import subprocess

        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
global:
  timeout: 30
instances:
  - name: test
    base_url: http://localhost:8080
    password: test-password-123
"""
            )
            temp_config = f.name

        try:
            result = subprocess.run(
                [
                    "python",
                    "-m",
                    "confighole.cli",
                    "-c",
                    temp_config,
                    "-i",
                    "nonexistent-instance",
                    "--dump",
                ],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 1
            assert "No instance found with name" in result.stderr

        finally:
            os.unlink(temp_config)
