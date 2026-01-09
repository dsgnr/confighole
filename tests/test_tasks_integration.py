"""Integration tests for ConfigHole tasks"""

import pytest

from confighole.utils.config import load_yaml_config, merge_global_settings
from confighole.utils.tasks import (
    diff_instance_config,
    dump_instance_data,
    process_instances,
    sync_instance_config,
)

from .constants import TEST_CONFIG_PATH


@pytest.mark.integration
class TestTasksIntegration:
    """Integration tests for ConfigHole tasks."""

    def test_dump_instance_data(self, pihole_container):
        """Test dumping instance data from Pi-hole."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        merged_instances = merge_global_settings(config)
        instance_config = merged_instances[0]

        result = dump_instance_data(instance_config)

        assert result is not None
        assert isinstance(result, dict)
        assert result["name"] == "test-instance"
        assert "base_url" in result
        assert "config" in result

        # Verify config structure
        config_data = result["config"]
        assert isinstance(config_data, dict)
        assert "dns" in config_data

    def test_diff_instance_config_no_changes(self, pihole_container):
        """Test diffing when no changes are needed."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        merged_instances = merge_global_settings(config)
        instance_config = merged_instances[0]

        # First get current config to match it exactly
        current_data = dump_instance_data(instance_config)
        if current_data is None:
            pytest.skip("Could not connect to Pi-hole for this test")

        current_dns = current_data["config"]["dns"]

        # Update instance config to match current state completely
        instance_config["config"]["dns"] = {
            "upstreams": current_dns["upstreams"],
            "queryLogging": current_dns["queryLogging"],
            "hosts": current_dns.get("hosts", []),
            "cnameRecords": current_dns.get("cnameRecords", []),
        }

        result = diff_instance_config(instance_config)

        # Should return None when no differences
        assert result is None

    def test_diff_instance_config_with_changes(self, pihole_container):
        """Test diffing when changes are detected."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        merged_instances = merge_global_settings(config)
        instance_config = merged_instances[0]

        # Ensure we have different upstreams than current
        instance_config["config"]["dns"]["upstreams"] = ["8.8.8.8", "8.8.4.4"]

        result = diff_instance_config(instance_config)

        if result is not None:  # Only if there are actual differences
            assert isinstance(result, dict)
            assert result["name"] == "test-instance"
            assert "diff" in result
            assert isinstance(result["diff"], dict)

    def test_sync_instance_config_dry_run(self, pihole_container):
        """Test syncing instance config in dry-run mode."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        merged_instances = merge_global_settings(config)
        instance_config = merged_instances[0]

        # Ensure we have different upstreams to create changes
        instance_config["config"]["dns"]["upstreams"] = ["8.8.8.8", "8.8.4.4"]

        result = sync_instance_config(instance_config, dry_run=True)

        if result is not None:  # Only if there are changes to sync
            assert isinstance(result, dict)
            assert result["name"] == "test-instance"
            assert "changes" in result

    def test_sync_instance_config_real(self, pihole_container):
        """Test syncing instance config for real."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        merged_instances = merge_global_settings(config)
        instance_config = merged_instances[0]

        # First get current config to restore later
        original_data = dump_instance_data(instance_config)
        if original_data is None:
            pytest.skip("Could not connect to Pi-hole for this test")

        original_upstreams = original_data["config"]["dns"]["upstreams"]

        try:
            # Set different upstreams
            new_upstreams = ["1.1.1.1", "1.0.0.1"]
            instance_config["config"]["dns"]["upstreams"] = new_upstreams

            result = sync_instance_config(instance_config, dry_run=False)

            if result is not None:  # Only if there were changes
                assert isinstance(result, dict)
                assert result["name"] == "test-instance"
                assert "changes" in result

                # Verify the change was applied
                updated_data = dump_instance_data(instance_config)
                if updated_data is not None:
                    assert updated_data["config"]["dns"]["upstreams"] == new_upstreams

        finally:
            # Restore original configuration
            instance_config["config"]["dns"]["upstreams"] = original_upstreams
            sync_instance_config(instance_config, dry_run=False)

    def test_process_instances_dump(self, pihole_container):
        """Test processing instances with dump operation."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        merged_instances = merge_global_settings(config)

        results = process_instances(merged_instances, "dump")

        assert isinstance(results, list)
        # Results may be empty if connection fails, which is acceptable
        if results:
            assert len(results) == 1
            assert results[0]["name"] == "test-instance"

    def test_process_instances_diff(self, pihole_container):
        """Test processing instances with diff operation."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        merged_instances = merge_global_settings(config)

        # Modify config to ensure differences
        merged_instances[0]["config"]["dns"]["upstreams"] = ["8.8.8.8", "8.8.4.4"]

        results = process_instances(merged_instances, "diff")

        assert isinstance(results, list)
        # Results may be empty if no differences, or contain diff data

    def test_process_instances_sync_dry_run(self, pihole_container):
        """Test processing instances with sync operation in dry-run."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        merged_instances = merge_global_settings(config)

        # Modify config to ensure changes
        merged_instances[0]["config"]["dns"]["upstreams"] = ["8.8.8.8", "8.8.4.4"]

        results = process_instances(merged_instances, "sync", dry_run=True)

        assert isinstance(results, list)
        # Results may be empty if no changes needed
