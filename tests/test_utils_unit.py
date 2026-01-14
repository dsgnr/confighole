"""Unit tests for utility functions."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from confighole.utils.config import (
    get_global_daemon_settings,
    load_yaml_config,
    merge_global_settings,
    resolve_password,
    validate_instance_config,
)
from confighole.utils.diff import (
    calculate_clients_diff,
    calculate_config_diff,
    calculate_domains_diff,
    calculate_groups_diff,
    calculate_lists_diff,
)
from confighole.utils.exceptions import ConfigurationError
from confighole.utils.helpers import (
    cnames_to_pihole_format,
    convert_diff_to_nested_dict,
    hosts_to_pihole_format,
    normalise_cname_records,
    normalise_configuration,
    normalise_dns_hosts,
    normalise_remote_domains,
)
from tests.constants import (
    SAMPLE_CLIENT,
    SAMPLE_DNS_CNAMES,
    SAMPLE_DNS_HOSTS,
    SAMPLE_DNS_UPSTREAMS,
    SAMPLE_DOMAIN,
    SAMPLE_GROUP,
    SAMPLE_LIST,
)


@pytest.mark.unit
class TestPasswordResolution:
    """Tests for password resolution from various sources."""

    def test_direct_password(self):
        """Direct password value is returned as-is."""
        config = {"password": "my-secret"}
        assert resolve_password(config) == "my-secret"

    def test_env_var_syntax(self):
        """Password with ${VAR} syntax resolves from environment."""
        os.environ["TEST_PW"] = "env-secret"
        try:
            config = {"password": "${TEST_PW}"}
            assert resolve_password(config) == "env-secret"
        finally:
            del os.environ["TEST_PW"]

    def test_env_var_missing(self):
        """Missing environment variable returns None."""
        config = {"password": "${NONEXISTENT_VAR}"}
        assert resolve_password(config) is None

    def test_password_env_field(self):
        """password_env field resolves from named environment variable."""
        os.environ["MY_PW_VAR"] = "another-secret"
        try:
            config = {"password_env": "MY_PW_VAR"}
            assert resolve_password(config) == "another-secret"
        finally:
            del os.environ["MY_PW_VAR"]

    def test_password_env_missing(self):
        """Missing password_env variable returns None."""
        config = {"password_env": "MISSING_VAR"}
        assert resolve_password(config) is None

    def test_no_password_configured(self):
        """No password configuration returns None."""
        config = {"name": "test"}
        assert resolve_password(config) is None

    def test_numeric_password_converted_to_string(self):
        """Numeric password is converted to string."""
        config = {"password": 12345}
        assert resolve_password(config) == "12345"


@pytest.mark.unit
class TestConfigMerging:
    """Tests for global settings merging into instances."""

    def test_empty_global_settings(self):
        """Empty global settings don't affect instances."""
        config = {
            "global": {},
            "instances": [{"name": "test", "base_url": "http://test"}],
        }
        result = merge_global_settings(config)

        assert len(result) == 1
        assert result[0]["name"] == "test"

    def test_global_settings_applied(self):
        """Global settings are applied to instances."""
        config = {
            "global": {"timeout": 30, "verify_ssl": False},
            "instances": [{"name": "test", "base_url": "http://test"}],
        }
        result = merge_global_settings(config)

        assert result[0]["timeout"] == 30
        assert result[0]["verify_ssl"] is False

    def test_instance_overrides_global(self):
        """Instance settings override global settings."""
        config = {
            "global": {"timeout": 30},
            "instances": [{"name": "test", "base_url": "http://test", "timeout": 60}],
        }
        result = merge_global_settings(config)

        assert result[0]["timeout"] == 60

    def test_daemon_settings_excluded(self):
        """Daemon-only settings are not merged into instances."""
        config = {
            "global": {"daemon_mode": True, "daemon_interval": 600, "timeout": 30},
            "instances": [{"name": "test", "base_url": "http://test"}],
        }
        result = merge_global_settings(config)

        assert "daemon_mode" not in result[0]
        assert "daemon_interval" not in result[0]
        assert result[0]["timeout"] == 30

    def test_no_instances(self):
        """Empty instances list returns empty list."""
        config = {"global": {"timeout": 30}, "instances": []}
        assert merge_global_settings(config) == []


@pytest.mark.unit
class TestDaemonSettings:
    """Tests for daemon settings extraction."""

    def test_defaults_when_empty(self):
        """Default values are returned when global is empty."""
        result = get_global_daemon_settings({"global": {}})

        assert result["daemon_mode"] is False
        assert result["daemon_interval"] == 300
        assert result["verbosity"] == 1
        assert result["dry_run"] is False

    def test_defaults_when_missing(self):
        """Default values are returned when global is missing."""
        result = get_global_daemon_settings({})

        assert result["daemon_mode"] is False
        assert result["daemon_interval"] == 300

    def test_custom_values(self):
        """Custom values are extracted correctly."""
        config = {
            "global": {
                "daemon_mode": True,
                "daemon_interval": 600,
                "verbosity": 2,
                "dry_run": True,
            }
        }
        result = get_global_daemon_settings(config)

        assert result["daemon_mode"] is True
        assert result["daemon_interval"] == 600
        assert result["verbosity"] == 2
        assert result["dry_run"] is True


@pytest.mark.unit
class TestYamlLoading:
    """Tests for YAML configuration loading."""

    def test_missing_file_exits(self):
        """Missing file causes system exit."""
        with pytest.raises(SystemExit):
            load_yaml_config("nonexistent.yaml")

    def test_invalid_yaml_exits(self):
        """Invalid YAML causes system exit."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: [unclosed")
            temp_file = f.name

        try:
            with pytest.raises(SystemExit):
                load_yaml_config(temp_file)
        finally:
            os.unlink(temp_file)

    def test_non_dict_yaml_exits(self):
        """YAML that isn't a dict causes system exit."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("- item1\n- item2")
            temp_file = f.name

        try:
            with pytest.raises(SystemExit):
                load_yaml_config(temp_file)
        finally:
            os.unlink(temp_file)


@pytest.mark.unit
class TestInstanceValidation:
    """Tests for instance configuration validation."""

    def test_valid_config_passes(self):
        """Valid configuration doesn't raise."""
        config = {"name": "test", "base_url": "http://test", "password": "secret"}
        validate_instance_config(config)

    def test_missing_base_url_raises(self):
        """Missing base_url raises ConfigurationError."""
        config = {"name": "test", "password": "secret"}
        with pytest.raises(ConfigurationError, match="missing required 'base_url'"):
            validate_instance_config(config)

    def test_empty_base_url_raises(self):
        """Empty base_url raises ConfigurationError."""
        config = {"name": "test", "base_url": "", "password": "secret"}
        with pytest.raises(ConfigurationError, match="missing required 'base_url'"):
            validate_instance_config(config)

    def test_missing_password_raises(self):
        """Missing password raises ConfigurationError."""
        config = {"name": "test", "base_url": "http://test"}
        with pytest.raises(ConfigurationError, match="has no password configured"):
            validate_instance_config(config)


@pytest.mark.unit
class TestConfigDiff:
    """Tests for configuration diff calculation."""

    def test_identical_configs_no_diff(self):
        """Identical configurations produce empty diff."""
        config = {"dns": {"upstreams": ["1.1.1.1"]}}
        assert calculate_config_diff(config, config) == {}

    def test_different_values_detected(self):
        """Different values are detected."""
        local = {"dns": {"upstreams": ["1.1.1.1"]}}
        remote = {"dns": {"upstreams": ["8.8.8.8"]}}

        result = calculate_config_diff(local, remote)

        assert "dns.upstreams" in result
        assert result["dns.upstreams"]["local"] == ["1.1.1.1"]
        assert result["dns.upstreams"]["remote"] == ["8.8.8.8"]

    def test_nested_changes_detected(self):
        """Nested changes are detected with dotted paths."""
        local = {"dns": {"domain": {"name": "test"}}}
        remote = {"dns": {"domain": {"name": "prod"}}}

        result = calculate_config_diff(local, remote)

        assert "dns.domain.name" in result

    def test_type_mismatch_detected(self):
        """Type mismatches are detected."""
        local = {"dns": {"upstreams": ["1.1.1.1"]}}
        remote = {"dns": {"upstreams": "1.1.1.1"}}

        result = calculate_config_diff(local, remote)

        assert "dns.upstreams" in result

    def test_none_remote_handled(self):
        """None remote config is handled gracefully."""
        local = {"dns": {"upstreams": ["1.1.1.1"]}}

        result = calculate_config_diff(local, None)

        assert "dns.upstreams" in result

    def test_empty_list_vs_populated(self):
        """Empty list vs populated list is detected."""
        local = {"dns": {"upstreams": []}}
        remote = {"dns": {"upstreams": ["1.1.1.1"]}}

        result = calculate_config_diff(local, remote)

        assert "dns.upstreams" in result
        assert result["dns.upstreams"]["local"] == []

    def test_list_order_ignored(self):
        """List order doesn't affect comparison for simple values."""
        local = {"dns": {"upstreams": ["1.1.1.1", "8.8.8.8"]}}
        remote = {"dns": {"upstreams": ["8.8.8.8", "1.1.1.1"]}}

        result = calculate_config_diff(local, remote)

        assert result == {}


@pytest.mark.unit
class TestListsDiff:
    """Tests for Pi-hole lists diff calculation."""

    def test_identical_lists_no_diff(self):
        """Identical lists produce empty diff."""
        lists = [SAMPLE_LIST]
        assert calculate_lists_diff(lists, lists) == {}

    def test_addition_detected(self):
        """New list in local is detected as addition."""
        local = [SAMPLE_LIST]
        remote: list[dict] = []

        result = calculate_lists_diff(local, remote)

        assert "add" in result
        assert len(result["add"]["local"]) == 1
        assert "remove" not in result

    def test_removal_detected(self):
        """List only in remote is detected as removal."""
        local: list[dict] = []
        remote = [SAMPLE_LIST]

        result = calculate_lists_diff(local, remote)

        assert "remove" in result
        assert len(result["remove"]["remote"]) == 1
        assert "add" not in result

    def test_change_detected(self):
        """Changed list properties are detected."""
        local = [{**SAMPLE_LIST, "comment": "Updated"}]
        remote = [SAMPLE_LIST]

        result = calculate_lists_diff(local, remote)

        assert "change" in result
        assert len(result["change"]["local"]) == 1

    def test_groups_order_ignored(self):
        """Group order doesn't affect comparison."""
        local = [{**SAMPLE_LIST, "groups": [0, 1]}]
        remote = [{**SAMPLE_LIST, "groups": [1, 0]}]

        assert calculate_lists_diff(local, remote) == {}

    def test_enabled_normalisation(self):
        """Truthy enabled values are treated as equal."""
        local = [{**SAMPLE_LIST, "enabled": True}]
        remote = [{**SAMPLE_LIST, "enabled": 1}]

        assert calculate_lists_diff(local, remote) == {}

    def test_none_remote_handled(self):
        """None remote lists handled as empty."""
        local = [SAMPLE_LIST]

        result = calculate_lists_diff(local, None)

        assert "add" in result


@pytest.mark.unit
class TestDnsNormalisation:
    """Tests for DNS record normalisation."""

    def test_hosts_dict_format_unchanged(self):
        """Dict format hosts are returned unchanged."""
        hosts = [{"ip": "192.168.1.1", "host": "test.local"}]
        assert normalise_dns_hosts(hosts) == hosts

    def test_hosts_string_format_parsed(self):
        """String format hosts are parsed to dicts."""
        hosts = ["192.168.1.1 test.local"]

        result = normalise_dns_hosts(hosts)

        assert result == [{"ip": "192.168.1.1", "host": "test.local"}]

    def test_hosts_multiple_spaces_handled(self):
        """Multiple spaces in host string are handled."""
        hosts = ["192.168.1.1   test.local"]

        result = normalise_dns_hosts(hosts)

        assert result[0]["host"] == "test.local"

    def test_hosts_missing_key_raises(self):
        """Dict missing required key raises error."""
        hosts = [{"ip": "192.168.1.1"}]

        with pytest.raises(ConfigurationError):
            normalise_dns_hosts(hosts)

    def test_hosts_invalid_format_raises(self):
        """Invalid format raises error."""
        with pytest.raises(ConfigurationError):
            normalise_dns_hosts([123])

        with pytest.raises(ConfigurationError):
            normalise_dns_hosts(["192.168.1.1"])  # No space

    def test_cnames_dict_format_unchanged(self):
        """Dict format CNAMEs are returned unchanged."""
        cnames = [{"name": "alias.test", "target": "real.test"}]
        assert normalise_cname_records(cnames) == cnames

    def test_cnames_string_format_parsed(self):
        """String format CNAMEs are parsed to dicts."""
        cnames = ["alias.test,real.test"]

        result = normalise_cname_records(cnames)

        assert result == [{"name": "alias.test", "target": "real.test"}]

    def test_cnames_whitespace_stripped(self):
        """Whitespace in CNAME strings is stripped."""
        cnames = [" alias.test , real.test "]

        result = normalise_cname_records(cnames)

        assert result == [{"name": "alias.test", "target": "real.test"}]

    def test_cnames_missing_key_raises(self):
        """Dict missing required key raises error."""
        cnames = [{"name": "alias.test"}]

        with pytest.raises(ConfigurationError):
            normalise_cname_records(cnames)

    def test_cnames_invalid_format_raises(self):
        """Invalid format raises error."""
        with pytest.raises(ConfigurationError):
            normalise_cname_records([123])

        with pytest.raises(ConfigurationError):
            normalise_cname_records(["alias.test"])  # No comma


@pytest.mark.unit
class TestConfigNormalisation:
    """Tests for full configuration normalisation."""

    def test_dns_section_normalised(self):
        """DNS section is normalised correctly."""
        config = {
            "dns": {
                "upstreams": SAMPLE_DNS_UPSTREAMS,
                "hosts": SAMPLE_DNS_HOSTS,
                "cnameRecords": SAMPLE_DNS_CNAMES,
            }
        }

        result = normalise_configuration(config)

        assert result["dns"]["hosts"] == SAMPLE_DNS_HOSTS
        assert result["dns"]["cnameRecords"] == SAMPLE_DNS_CNAMES

    def test_no_dns_section_unchanged(self):
        """Config without DNS section is unchanged."""
        config = {"other": "data"}
        assert normalise_configuration(config) == config

    def test_invalid_dns_section_unchanged(self):
        """Non-dict DNS section is unchanged."""
        config = {"dns": "not_a_dict"}
        assert normalise_configuration(config) == config

    def test_empty_config_returns_empty(self):
        """Empty config returns empty dict."""
        assert normalise_configuration({}) == {}


@pytest.mark.unit
class TestPiholeFormatConversion:
    """Tests for converting to Pi-hole API format."""

    def test_hosts_to_pihole_format(self):
        """Hosts are converted to space-separated strings."""
        hosts = [
            {"ip": "192.168.1.1", "host": "gateway.test"},
            {"ip": "192.168.1.10", "host": "nas.test"},
        ]

        result = hosts_to_pihole_format(hosts)

        assert result == ["192.168.1.1 gateway.test", "192.168.1.10 nas.test"]

    def test_cnames_to_pihole_format(self):
        """CNAMEs are converted to comma-separated strings."""
        cnames = [
            {"name": "plex.test", "target": "nas.test"},
            {"name": "grafana.test", "target": "gateway.test"},
        ]

        result = cnames_to_pihole_format(cnames)

        assert result == ["plex.test,nas.test", "grafana.test,gateway.test"]


@pytest.mark.unit
class TestDiffToNestedDict:
    """Tests for converting flat diff to nested structure."""

    def test_simple_conversion(self):
        """Simple paths are converted correctly."""
        diff = {
            "dns.upstreams": {"local": ["1.1.1.1"], "remote": ["8.8.8.8"]},
        }

        result = convert_diff_to_nested_dict(diff)

        assert result["dns"]["upstreams"] == ["1.1.1.1"]

    def test_multiple_paths_merged(self):
        """Multiple paths are merged correctly."""
        diff = {
            "dns.upstreams": {"local": ["1.1.1.1"], "remote": []},
            "dns.queryLogging": {"local": True, "remote": False},
        }

        result = convert_diff_to_nested_dict(diff)

        assert result["dns"]["upstreams"] == ["1.1.1.1"]
        assert result["dns"]["queryLogging"] is True

    def test_hosts_converted_to_pihole_format(self):
        """Hosts are converted to Pi-hole string format."""
        diff = {
            "dns.hosts": {
                "local": [{"ip": "192.168.1.1", "host": "test.local"}],
                "remote": [],
            }
        }

        result = convert_diff_to_nested_dict(diff)

        assert result["dns"]["hosts"] == ["192.168.1.1 test.local"]

    def test_cnames_converted_to_pihole_format(self):
        """CNAMEs are converted to Pi-hole string format."""
        diff = {
            "dns.cnameRecords": {
                "local": [{"name": "alias.test", "target": "real.test"}],
                "remote": [],
            }
        }

        result = convert_diff_to_nested_dict(diff)

        assert result["dns"]["cnameRecords"] == ["alias.test,real.test"]


@pytest.mark.unit
class TestTaskOperations:
    """Tests for task operation functions."""

    def test_process_instances_invalid_operation(self):
        """Invalid operation raises ValueError."""
        from confighole.utils.tasks import process_instances

        with pytest.raises(ValueError, match="Unknown operation"):
            process_instances([{"name": "test"}], "invalid")

    @patch("confighole.utils.tasks.create_manager")
    def test_dump_returns_none_when_manager_fails(self, mock_create_manager):
        """dump_instance_data returns None when manager creation fails."""
        from confighole.utils.tasks import dump_instance_data

        mock_create_manager.return_value = None

        result = dump_instance_data({"name": "test", "base_url": "http://test"})

        assert result is None

    def test_diff_returns_none_without_local_config(self):
        """diff_instance_config returns None without local config."""
        from confighole.utils.tasks import diff_instance_config

        result = diff_instance_config({"name": "test", "base_url": "http://test"})

        assert result is None

    def test_sync_config_returns_none_without_local_config(self):
        """sync_instance_config returns None without local config."""
        from confighole.utils.tasks import sync_instance_config

        result = sync_instance_config({"name": "test", "base_url": "http://test"})

        assert result is None

    def test_sync_lists_returns_none_without_local_lists(self):
        """sync_list_config returns None without local lists."""
        from confighole.utils.tasks import sync_list_config

        result = sync_list_config({"name": "test", "base_url": "http://test"})

        assert result is None

    @patch("confighole.utils.tasks.create_manager")
    def test_sync_lists_calls_update(self, mock_create_manager):
        """sync_list_config calls update_lists on manager."""
        from confighole.utils.tasks import sync_list_config

        mock_manager = MagicMock()
        mock_manager.__enter__.return_value = mock_manager
        mock_manager.fetch_lists.return_value = []
        mock_manager.update_lists.return_value = True
        mock_create_manager.return_value = mock_manager

        config = {
            "name": "test",
            "base_url": "http://test",
            "lists": [SAMPLE_LIST],
        }

        result = sync_list_config(config, dry_run=False)

        assert result is not None
        assert result["name"] == "test"
        mock_manager.update_lists.assert_called_once()

    @patch("confighole.utils.tasks.create_manager")
    def test_dump_handles_exception(self, mock_create_manager):
        """dump_instance_data handles exceptions gracefully."""
        from confighole.utils.tasks import dump_instance_data

        mock_manager = MagicMock()
        mock_manager.__enter__.side_effect = Exception("Connection failed")
        mock_create_manager.return_value = mock_manager

        result = dump_instance_data(
            {
                "name": "test",
                "base_url": "http://test",
                "password": "test",
            }
        )

        assert result is None


@pytest.mark.unit
class TestDomainNormalisation:
    """Tests for domain normalisation."""

    def test_normalise_remote_domains(self):
        """Remote domains are normalised correctly."""
        from pihole_lib.models.domains import Domain, DomainKind, DomainType

        domains = [
            Domain(
                domain="blocked.example.com",
                unicode="blocked.example.com",
                type=DomainType.DENY,
                kind=DomainKind.EXACT,
                comment="Test domain",
                groups=[0],
                enabled=True,
                id=1,
                date_added=1234567890,
                date_modified=1234567890,
            ),
            Domain(
                domain=r".*\.ads\..*",
                unicode=r".*\.ads\..*",
                type=DomainType.DENY,
                kind=DomainKind.REGEX,
                comment="Block ads",
                groups=[0, 1],
                enabled=False,
                id=2,
                date_added=1234567890,
                date_modified=1234567890,
            ),
        ]

        result = normalise_remote_domains(domains)

        assert len(result) == 2
        assert result[0]["domain"] == "blocked.example.com"
        assert result[0]["type"] == "deny"
        assert result[0]["kind"] == "exact"
        assert result[0]["comment"] == "Test domain"
        assert result[0]["groups"] == [0]
        assert result[0]["enabled"] is True

        assert result[1]["domain"] == r".*\.ads\..*"
        assert result[1]["type"] == "deny"
        assert result[1]["kind"] == "regex"
        assert result[1]["enabled"] is False

    def test_normalise_remote_domains_empty(self):
        """Empty domain list returns empty list."""
        result = normalise_remote_domains([])
        assert result == []


@pytest.mark.unit
class TestDomainsDiff:
    """Tests for Pi-hole domains diff calculation."""

    def test_identical_domains_no_diff(self):
        """Identical domains produce empty diff."""
        domains = [SAMPLE_DOMAIN]
        assert calculate_domains_diff(domains, domains) == {}

    def test_addition_detected(self):
        """New domain in local is detected as addition."""
        local = [SAMPLE_DOMAIN]
        remote: list[dict] = []

        result = calculate_domains_diff(local, remote)

        assert "add" in result
        assert len(result["add"]["local"]) == 1
        assert "remove" not in result

    def test_removal_detected(self):
        """Domain only in remote is detected as removal."""
        local: list[dict] = []
        remote = [SAMPLE_DOMAIN]

        result = calculate_domains_diff(local, remote)

        assert "remove" in result
        assert len(result["remove"]["remote"]) == 1
        assert "add" not in result

    def test_change_detected(self):
        """Changed domain properties are detected."""
        local = [{**SAMPLE_DOMAIN, "comment": "Updated"}]
        remote = [SAMPLE_DOMAIN]

        result = calculate_domains_diff(local, remote)

        assert "change" in result
        assert len(result["change"]["local"]) == 1

    def test_groups_order_ignored(self):
        """Group order doesn't affect comparison."""
        local = [{**SAMPLE_DOMAIN, "groups": [0, 1]}]
        remote = [{**SAMPLE_DOMAIN, "groups": [1, 0]}]

        assert calculate_domains_diff(local, remote) == {}

    def test_enabled_normalisation(self):
        """Truthy enabled values are treated as equal."""
        local = [{**SAMPLE_DOMAIN, "enabled": True}]
        remote = [{**SAMPLE_DOMAIN, "enabled": 1}]

        assert calculate_domains_diff(local, remote) == {}

    def test_none_remote_handled(self):
        """None remote domains handled as empty."""
        local = [SAMPLE_DOMAIN]

        result = calculate_domains_diff(local, None)

        assert "add" in result

    def test_different_type_treated_as_different_domain(self):
        """Same domain with different type is treated as different."""
        local = [{**SAMPLE_DOMAIN, "type": "allow"}]
        remote = [SAMPLE_DOMAIN]  # type is "deny"

        result = calculate_domains_diff(local, remote)

        assert "add" in result
        assert "remove" in result

    def test_different_kind_treated_as_different_domain(self):
        """Same domain with different kind is treated as different."""
        local = [{**SAMPLE_DOMAIN, "kind": "regex"}]
        remote = [SAMPLE_DOMAIN]  # kind is "exact"

        result = calculate_domains_diff(local, remote)

        assert "add" in result
        assert "remove" in result


@pytest.mark.unit
class TestSyncDomainConfig:
    """Tests for sync_domain_config function."""

    def test_sync_domains_returns_none_without_local_domains(self):
        """sync_domain_config returns None without local domains."""
        from confighole.utils.tasks import sync_domain_config

        result = sync_domain_config({"name": "test", "base_url": "http://test"})

        assert result is None

    @patch("confighole.utils.tasks.create_manager")
    def test_sync_domains_calls_update(self, mock_create_manager):
        """sync_domain_config calls update_domains on manager."""
        from confighole.utils.tasks import sync_domain_config

        mock_manager = MagicMock()
        mock_manager.__enter__.return_value = mock_manager
        mock_manager.fetch_domains.return_value = []
        mock_manager.update_domains.return_value = True
        mock_create_manager.return_value = mock_manager

        config = {
            "name": "test",
            "base_url": "http://test",
            "domains": [SAMPLE_DOMAIN],
        }

        result = sync_domain_config(config, dry_run=False)

        assert result is not None
        assert result["name"] == "test"
        mock_manager.update_domains.assert_called_once()

    @patch("confighole.utils.tasks.create_manager")
    def test_sync_domains_no_changes_returns_none(self, mock_create_manager):
        """sync_domain_config returns None when no changes needed."""
        from confighole.utils.tasks import sync_domain_config

        mock_manager = MagicMock()
        mock_manager.__enter__.return_value = mock_manager
        mock_manager.fetch_domains.return_value = [SAMPLE_DOMAIN]
        mock_create_manager.return_value = mock_manager

        config = {
            "name": "test",
            "base_url": "http://test",
            "domains": [SAMPLE_DOMAIN],
        }

        result = sync_domain_config(config, dry_run=False)

        assert result is None

    @patch("confighole.utils.tasks.create_manager")
    def test_sync_domains_dry_run(self, mock_create_manager):
        """sync_domain_config dry run doesn't call update."""
        from confighole.utils.tasks import sync_domain_config

        mock_manager = MagicMock()
        mock_manager.__enter__.return_value = mock_manager
        mock_manager.fetch_domains.return_value = []
        mock_create_manager.return_value = mock_manager

        config = {
            "name": "test",
            "base_url": "http://test",
            "domains": [SAMPLE_DOMAIN],
        }

        result = sync_domain_config(config, dry_run=True)

        assert result is not None
        mock_manager.update_domains.assert_not_called()


@pytest.mark.unit
class TestGroupsDiff:
    """Tests for Pi-hole groups diff calculation."""

    def test_identical_groups_no_diff(self):
        """Identical groups produce empty diff."""
        groups = [SAMPLE_GROUP]
        assert calculate_groups_diff(groups, groups) == {}

    def test_addition_detected(self):
        """New group in local is detected as addition."""
        local = [SAMPLE_GROUP]
        remote: list[dict] = []

        result = calculate_groups_diff(local, remote)

        assert "add" in result
        assert len(result["add"]["local"]) == 1
        assert "remove" not in result

    def test_removal_detected(self):
        """Group only in remote is detected as removal."""
        local: list[dict] = []
        remote = [SAMPLE_GROUP]

        result = calculate_groups_diff(local, remote)

        assert "remove" in result
        assert len(result["remove"]["remote"]) == 1
        assert "add" not in result

    def test_change_detected(self):
        """Changed group properties are detected."""
        local = [{**SAMPLE_GROUP, "comment": "Updated"}]
        remote = [SAMPLE_GROUP]

        result = calculate_groups_diff(local, remote)

        assert "change" in result
        assert len(result["change"]["local"]) == 1

    def test_enabled_normalisation(self):
        """Truthy enabled values are treated as equal."""
        local = [{**SAMPLE_GROUP, "enabled": True}]
        remote = [{**SAMPLE_GROUP, "enabled": 1}]

        assert calculate_groups_diff(local, remote) == {}

    def test_none_remote_handled(self):
        """None remote groups handled as empty."""
        local = [SAMPLE_GROUP]

        result = calculate_groups_diff(local, None)

        assert "add" in result


@pytest.mark.unit
class TestSyncGroupConfig:
    """Tests for sync_group_config function."""

    def test_sync_groups_returns_none_without_local_groups(self):
        """sync_group_config returns None without local groups."""
        from confighole.utils.tasks import sync_group_config

        result = sync_group_config({"name": "test", "base_url": "http://test"})

        assert result is None

    @patch("confighole.utils.tasks.create_manager")
    def test_sync_groups_calls_update(self, mock_create_manager):
        """sync_group_config calls update_groups on manager."""
        from confighole.utils.tasks import sync_group_config

        mock_manager = MagicMock()
        mock_manager.__enter__.return_value = mock_manager
        mock_manager.fetch_groups.return_value = []
        mock_manager.update_groups.return_value = True
        mock_create_manager.return_value = mock_manager

        config = {
            "name": "test",
            "base_url": "http://test",
            "groups": [SAMPLE_GROUP],
        }

        result = sync_group_config(config, dry_run=False)

        assert result is not None
        assert result["name"] == "test"
        mock_manager.update_groups.assert_called_once()

    @patch("confighole.utils.tasks.create_manager")
    def test_sync_groups_no_changes_returns_none(self, mock_create_manager):
        """sync_group_config returns None when no changes needed."""
        from confighole.utils.tasks import sync_group_config

        mock_manager = MagicMock()
        mock_manager.__enter__.return_value = mock_manager
        mock_manager.fetch_groups.return_value = [SAMPLE_GROUP]
        mock_create_manager.return_value = mock_manager

        config = {
            "name": "test",
            "base_url": "http://test",
            "groups": [SAMPLE_GROUP],
        }

        result = sync_group_config(config, dry_run=False)

        assert result is None


@pytest.mark.unit
class TestClientsDiff:
    """Tests for Pi-hole clients diff calculation."""

    def test_identical_clients_no_diff(self):
        """Identical clients produce empty diff."""
        clients = [SAMPLE_CLIENT]
        assert calculate_clients_diff(clients, clients) == {}

    def test_addition_detected(self):
        """New client in local is detected as addition."""
        local = [SAMPLE_CLIENT]
        remote: list[dict] = []

        result = calculate_clients_diff(local, remote)

        assert "add" in result
        assert len(result["add"]["local"]) == 1
        assert "remove" not in result

    def test_removal_detected(self):
        """Client only in remote is detected as removal."""
        local: list[dict] = []
        remote = [SAMPLE_CLIENT]

        result = calculate_clients_diff(local, remote)

        assert "remove" in result
        assert len(result["remove"]["remote"]) == 1
        assert "add" not in result

    def test_change_detected(self):
        """Changed client properties are detected."""
        local = [{**SAMPLE_CLIENT, "comment": "Updated"}]
        remote = [SAMPLE_CLIENT]

        result = calculate_clients_diff(local, remote)

        assert "change" in result
        assert len(result["change"]["local"]) == 1

    def test_groups_order_ignored(self):
        """Group order doesn't affect comparison."""
        local = [{**SAMPLE_CLIENT, "groups": [0, 1]}]
        remote = [{**SAMPLE_CLIENT, "groups": [1, 0]}]

        assert calculate_clients_diff(local, remote) == {}

    def test_none_remote_handled(self):
        """None remote clients handled as empty."""
        local = [SAMPLE_CLIENT]

        result = calculate_clients_diff(local, None)

        assert "add" in result


@pytest.mark.unit
class TestSyncClientConfig:
    """Tests for sync_client_config function."""

    def test_sync_clients_returns_none_without_local_clients(self):
        """sync_client_config returns None without local clients."""
        from confighole.utils.tasks import sync_client_config

        result = sync_client_config({"name": "test", "base_url": "http://test"})

        assert result is None

    @patch("confighole.utils.tasks.create_manager")
    def test_sync_clients_calls_update(self, mock_create_manager):
        """sync_client_config calls update_clients on manager."""
        from confighole.utils.tasks import sync_client_config

        mock_manager = MagicMock()
        mock_manager.__enter__.return_value = mock_manager
        mock_manager.fetch_clients.return_value = []
        mock_manager.update_clients.return_value = True
        mock_create_manager.return_value = mock_manager

        config = {
            "name": "test",
            "base_url": "http://test",
            "clients": [SAMPLE_CLIENT],
        }

        result = sync_client_config(config, dry_run=False)

        assert result is not None
        assert result["name"] == "test"
        mock_manager.update_clients.assert_called_once()

    @patch("confighole.utils.tasks.create_manager")
    def test_sync_clients_no_changes_returns_none(self, mock_create_manager):
        """sync_client_config returns None when no changes needed."""
        from confighole.utils.tasks import sync_client_config

        mock_manager = MagicMock()
        mock_manager.__enter__.return_value = mock_manager
        mock_manager.fetch_clients.return_value = [SAMPLE_CLIENT]
        mock_create_manager.return_value = mock_manager

        config = {
            "name": "test",
            "base_url": "http://test",
            "clients": [SAMPLE_CLIENT],
        }

        result = sync_client_config(config, dry_run=False)

        assert result is None


@pytest.mark.unit
class TestSyncListConfigWithGravity:
    """Tests for sync_list_config with gravity update."""

    @patch("confighole.utils.tasks.create_manager")
    def test_sync_lists_updates_gravity_when_enabled(self, mock_create_manager):
        """sync_list_config calls update_gravity when enabled."""
        from confighole.utils.tasks import sync_list_config

        mock_manager = MagicMock()
        mock_manager.__enter__.return_value = mock_manager
        mock_manager.fetch_lists.return_value = []
        mock_manager.update_lists.return_value = True
        mock_manager.update_gravity.return_value = True
        mock_create_manager.return_value = mock_manager

        config = {
            "name": "test",
            "base_url": "http://test",
            "lists": [SAMPLE_LIST],
            "update_gravity": True,
        }

        result = sync_list_config(config, dry_run=False)

        assert result is not None
        mock_manager.update_gravity.assert_called_once()

    @patch("confighole.utils.tasks.create_manager")
    def test_sync_lists_skips_gravity_when_disabled(self, mock_create_manager):
        """sync_list_config skips update_gravity when disabled."""
        from confighole.utils.tasks import sync_list_config

        mock_manager = MagicMock()
        mock_manager.__enter__.return_value = mock_manager
        mock_manager.fetch_lists.return_value = []
        mock_manager.update_lists.return_value = True
        mock_create_manager.return_value = mock_manager

        config = {
            "name": "test",
            "base_url": "http://test",
            "lists": [SAMPLE_LIST],
            "update_gravity": False,
        }

        result = sync_list_config(config, dry_run=False)

        assert result is not None
        mock_manager.update_gravity.assert_not_called()

    @patch("confighole.utils.tasks.create_manager")
    def test_sync_lists_skips_gravity_by_default(self, mock_create_manager):
        """sync_list_config skips update_gravity by default."""
        from confighole.utils.tasks import sync_list_config

        mock_manager = MagicMock()
        mock_manager.__enter__.return_value = mock_manager
        mock_manager.fetch_lists.return_value = []
        mock_manager.update_lists.return_value = True
        mock_create_manager.return_value = mock_manager

        config = {
            "name": "test",
            "base_url": "http://test",
            "lists": [SAMPLE_LIST],
        }

        result = sync_list_config(config, dry_run=False)

        assert result is not None
        mock_manager.update_gravity.assert_not_called()

    @patch("confighole.utils.tasks.create_manager")
    def test_sync_lists_dry_run_skips_gravity(self, mock_create_manager):
        """sync_list_config dry run doesn't call update_gravity."""
        from confighole.utils.tasks import sync_list_config

        mock_manager = MagicMock()
        mock_manager.__enter__.return_value = mock_manager
        mock_manager.fetch_lists.return_value = []
        mock_create_manager.return_value = mock_manager

        config = {
            "name": "test",
            "base_url": "http://test",
            "lists": [SAMPLE_LIST],
            "update_gravity": True,
        }

        result = sync_list_config(config, dry_run=True)

        assert result is not None
        mock_manager.update_gravity.assert_not_called()
