"""Integration tests for ConfigHole Pi-hole client"""

import pytest

from confighole.core.client import PiHoleManager, create_manager
from confighole.utils.config import load_yaml_config, merge_global_settings

from .constants import PIHOLE_BASE_URL, PIHOLE_TEST_PASSWORD, TEST_CONFIG_PATH


@pytest.mark.integration
class TestClientIntegration:
    """Integration tests for Pi-hole client operations."""

    def test_create_confighole_from_config(self, pihole_container):
        """Test creating PiHoleManager from configuration."""
        config = load_yaml_config(TEST_CONFIG_PATH)
        merged_instances = merge_global_settings(config)
        instance_config = merged_instances[0]

        manager = create_manager(instance_config)

        assert manager is not None
        assert isinstance(manager, PiHoleManager)
        assert manager.base_url == PIHOLE_BASE_URL
        assert manager.password == PIHOLE_TEST_PASSWORD
        assert manager.timeout == 30
        assert manager.verify_ssl is False

    def test_pihole_manager_context_manager(self, pihole_container):
        """Test PiHoleManager as context manager."""
        manager = PiHoleManager(
            base_url=PIHOLE_BASE_URL,
            password=PIHOLE_TEST_PASSWORD,
            verify_ssl=False,
        )

        with manager:
            # Should be able to use the manager
            assert manager._client is not None

        # Client should be cleaned up after context exit
        # Note: We can't easily test this without accessing private attributes

    def test_fetch_configuration(self, pihole_container):
        """Test fetching configuration from Pi-hole."""
        manager = PiHoleManager(
            base_url=PIHOLE_BASE_URL,
            password=PIHOLE_TEST_PASSWORD,
            verify_ssl=False,
        )

        with manager:
            config = manager.fetch_configuration()

            # Verify response structure
            assert isinstance(config, dict)
            assert "dns" in config

            # Verify DNS section
            dns_config = config["dns"]
            assert isinstance(dns_config, dict)
            assert "upstreams" in dns_config
            assert "queryLogging" in dns_config

    def test_update_configuration_dry_run(self, pihole_container):
        """Test updating configuration in dry-run mode."""
        manager = PiHoleManager(
            base_url=PIHOLE_BASE_URL,
            password=PIHOLE_TEST_PASSWORD,
            verify_ssl=False,
        )

        test_changes = {
            "dns": {
                "upstreams": ["8.8.8.8", "8.8.4.4"],
            }
        }

        with manager:
            # Dry run should always return True
            result = manager.update_configuration(test_changes, dry_run=True)
            assert result is True

    def test_update_configuration_real(self, pihole_container):
        """Test updating configuration for real."""
        manager = PiHoleManager(
            base_url=PIHOLE_BASE_URL,
            password=PIHOLE_TEST_PASSWORD,
            verify_ssl=False,
        )

        # First get current config
        with manager:
            original_config = manager.fetch_configuration()
            original_upstreams = original_config["dns"]["upstreams"]

            # Update with new upstreams
            new_upstreams = ["1.1.1.1", "1.0.0.1"]
            test_changes = {"dns": {"upstreams": new_upstreams}}

            result = manager.update_configuration(test_changes, dry_run=False)
            assert result is True

            # Verify the change was applied
            updated_config = manager.fetch_configuration()
            assert updated_config["dns"]["upstreams"] == new_upstreams

            # Restore original configuration
            restore_changes = {"dns": {"upstreams": original_upstreams}}
            restore_result = manager.update_configuration(
                restore_changes, dry_run=False
            )
            assert restore_result is True
