"""Unit tests for Pi-hole client."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from confighole.core.client import PiHoleManager, create_manager


@pytest.mark.unit
class TestPiHoleManagerInit:
    """Tests for PiHoleManager initialisation."""

    def test_empty_password_raises(self):
        """Empty password raises ValueError."""
        with pytest.raises(ValueError, match="Password cannot be None or empty"):
            PiHoleManager("http://test", "")

    def test_none_password_raises(self):
        """None password raises ValueError."""
        with pytest.raises(ValueError, match="Password cannot be None or empty"):
            PiHoleManager("http://test", None)

    def test_attributes_set_correctly(self):
        """Attributes are set correctly."""
        manager = PiHoleManager(
            "http://test",
            "password",
            timeout=60,
            verify_ssl=False,
        )

        assert manager.base_url == "http://test"
        assert manager.password == "password"
        assert manager.timeout == 60
        assert manager.verify_ssl is False
        assert manager._client is None

    def test_default_values(self):
        """Default values are applied."""
        manager = PiHoleManager("http://test", "password")

        assert manager.timeout == 30
        assert manager.verify_ssl is True


@pytest.mark.unit
class TestPiHoleManagerOperations:
    """Tests for PiHoleManager operations."""

    def test_fetch_config_not_initialised_raises(self):
        """fetch_configuration raises when not initialised."""
        manager = PiHoleManager("http://test", "password")

        with pytest.raises(RuntimeError, match="Client not initialised"):
            manager.fetch_configuration()

    def test_fetch_lists_not_initialised_raises(self):
        """fetch_lists raises when not initialised."""
        manager = PiHoleManager("http://test", "password")

        with pytest.raises(RuntimeError, match="Client not initialised"):
            manager.fetch_lists()

    def test_fetch_domains_not_initialised_raises(self):
        """fetch_domains raises when not initialised."""
        manager = PiHoleManager("http://test", "password")

        with pytest.raises(RuntimeError, match="Client not initialised"):
            manager.fetch_domains()

    def test_update_config_not_initialised_raises(self):
        """update_configuration raises when not initialised."""
        manager = PiHoleManager("http://test", "password")

        with pytest.raises(RuntimeError, match="Client not initialised"):
            manager.update_configuration({"dns": {}})

    def test_update_lists_not_initialised_raises(self):
        """update_lists raises when not initialised."""
        manager = PiHoleManager("http://test", "password")

        with pytest.raises(RuntimeError, match="Client not initialised"):
            manager.update_lists({"add": {}})

    def test_update_domains_not_initialised_raises(self):
        """update_domains raises when not initialised."""
        manager = PiHoleManager("http://test", "password")

        with pytest.raises(RuntimeError, match="Client not initialised"):
            manager.update_domains({"add": {}})

    def test_update_config_empty_changes_returns_true(self):
        """Empty changes returns True without calling API."""
        manager = PiHoleManager("http://test", "password")
        manager._client = Mock()

        result = manager.update_configuration({})

        assert result is True
        manager._client.config.update_config.assert_not_called()

    def test_update_lists_empty_changes_returns_true(self):
        """Empty list changes returns True without calling API."""
        manager = PiHoleManager("http://test", "password")
        manager._client = Mock()

        result = manager.update_lists({})

        assert result is True

    def test_update_domains_empty_changes_returns_true(self):
        """Empty domain changes returns True without calling API."""
        manager = PiHoleManager("http://test", "password")
        manager._client = Mock()

        result = manager.update_domains({})

        assert result is True

    def test_update_config_dry_run_returns_true(self):
        """Dry run returns True without calling API."""
        manager = PiHoleManager("http://test", "password")
        manager._client = Mock()

        result = manager.update_configuration({"dns": {}}, dry_run=True)

        assert result is True
        manager._client.config.update_config.assert_not_called()

    def test_update_lists_dry_run_returns_true(self):
        """Dry run returns True without calling API."""
        manager = PiHoleManager("http://test", "password")
        manager._client = Mock()

        result = manager.update_lists({"add": {"local": []}}, dry_run=True)

        assert result is True

    def test_update_domains_dry_run_returns_true(self):
        """Dry run returns True without calling API."""
        manager = PiHoleManager("http://test", "password")
        manager._client = Mock()

        result = manager.update_domains({"add": {"local": []}}, dry_run=True)

        assert result is True

    @patch("confighole.core.client.PiHoleClient")
    def test_update_config_failure_returns_false(self, mock_client_class):
        """API failure returns False."""
        mock_client = Mock()
        mock_client.config.update_config.side_effect = Exception("API Error")
        mock_client_class.return_value = mock_client

        manager = PiHoleManager("http://test", "password")
        manager._client = mock_client

        result = manager.update_configuration({"dns": {}})

        assert result is False


@pytest.mark.unit
class TestCreateManager:
    """Tests for create_manager factory function."""

    def test_missing_base_url_returns_none(self):
        """Missing base_url returns None."""
        config = {"name": "test", "password": "secret"}

        result = create_manager(config)

        assert result is None

    def test_missing_password_returns_none(self):
        """Missing password returns None."""
        config = {"name": "test", "base_url": "http://test"}

        result = create_manager(config)

        assert result is None

    def test_valid_config_returns_manager(self):
        """Valid config returns PiHoleManager."""
        config = {
            "name": "test",
            "base_url": "http://test",
            "password": "secret",
        }

        result = create_manager(config)

        assert result is not None
        assert isinstance(result, PiHoleManager)
        assert result.base_url == "http://test"
        assert result.password == "secret"

    def test_env_password_resolved(self):
        """Environment variable password is resolved."""
        os.environ["TEST_PW"] = "env-secret"

        try:
            config = {
                "name": "test",
                "base_url": "http://test",
                "password": "${TEST_PW}",
            }

            result = create_manager(config)

            assert result is not None
            assert result.password == "env-secret"
        finally:
            del os.environ["TEST_PW"]

    def test_missing_env_password_returns_none(self):
        """Missing environment variable returns None."""
        config = {
            "name": "test",
            "base_url": "http://test",
            "password": "${MISSING_VAR}",
        }

        result = create_manager(config)

        assert result is None

    def test_custom_timeout_and_ssl(self):
        """Custom timeout and SSL settings are applied."""
        config = {
            "name": "test",
            "base_url": "http://test",
            "password": "secret",
            "timeout": 60,
            "verify_ssl": False,
        }

        result = create_manager(config)

        assert result.timeout == 60
        assert result.verify_ssl is False


@pytest.mark.unit
class TestPiHoleManagerContextManager:
    """Tests for PiHoleManager context manager."""

    @patch("confighole.core.client.PiHoleClient")
    def test_enter_creates_client(self, mock_client_class):
        """__enter__ creates and authenticates client."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        manager = PiHoleManager("http://test", "password")

        with manager:
            assert manager._client is not None
            mock_client.__enter__.assert_called_once()

    @patch("confighole.core.client.PiHoleClient")
    def test_exit_cleans_up_client(self, mock_client_class):
        """__exit__ cleans up client."""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        manager = PiHoleManager("http://test", "password")

        with manager:
            pass

        mock_client.__exit__.assert_called_once()

    @patch("confighole.core.client.PiHoleClient")
    def test_enter_failure_raises(self, mock_client_class):
        """__enter__ failure raises exception."""
        mock_client_class.side_effect = Exception("Connection failed")

        manager = PiHoleManager("http://test", "password")

        with pytest.raises(Exception, match="Connection failed"):
            with manager:
                pass


@pytest.mark.unit
class TestListOperations:
    """Tests for list update operations."""

    def test_apply_list_additions(self):
        """List additions are applied correctly."""
        manager = PiHoleManager("http://test", "password")
        mock_client = MagicMock()
        manager._client = mock_client

        changes = {
            "add": {
                "local": [
                    {
                        "address": "https://example.com/list.txt",
                        "type": "block",
                        "comment": "Test",
                        "groups": [0],
                        "enabled": True,
                    }
                ]
            }
        }

        manager._apply_list_additions(mock_client, changes)

        mock_client.lists.add_list.assert_called_once()

    def test_apply_list_removals(self):
        """List removals are applied correctly."""
        manager = PiHoleManager("http://test", "password")
        mock_client = MagicMock()
        manager._client = mock_client

        changes = {
            "remove": {
                "remote": [{"address": "https://example.com/list.txt", "type": "block"}]
            }
        }

        manager._apply_list_removals(mock_client, changes)

        mock_client.lists.batch_delete_lists.assert_called_once()

    def test_apply_list_changes(self):
        """List changes delete old and add new."""
        manager = PiHoleManager("http://test", "password")
        mock_client = MagicMock()
        manager._client = mock_client

        changes = {
            "change": {
                "local": [
                    {
                        "address": "https://example.com/list.txt",
                        "type": "block",
                        "comment": "Updated",
                    }
                ],
                "remote": [
                    {"address": "https://example.com/list.txt", "type": "block"}
                ],
            }
        }

        manager._apply_list_changes(mock_client, changes)

        mock_client.lists.batch_delete_lists.assert_called_once()
        mock_client.lists.update_list.assert_called_once()


@pytest.mark.unit
class TestDomainOperations:
    """Tests for domain update operations."""

    def test_apply_domain_additions(self):
        """Domain additions are applied correctly."""
        manager = PiHoleManager("http://test", "password")
        mock_client = MagicMock()
        manager._client = mock_client

        changes = {
            "add": {
                "local": [
                    {
                        "domain": "blocked.example.com",
                        "type": "deny",
                        "kind": "exact",
                        "comment": "Test",
                        "groups": [0],
                        "enabled": True,
                    }
                ]
            }
        }

        manager._apply_domain_additions(mock_client, changes)

        mock_client.domains.add_domain.assert_called_once()

    def test_apply_domain_removals(self):
        """Domain removals are applied correctly."""
        manager = PiHoleManager("http://test", "password")
        mock_client = MagicMock()
        manager._client = mock_client

        changes = {
            "remove": {
                "remote": [
                    {
                        "domain": "blocked.example.com",
                        "type": "deny",
                        "kind": "exact",
                    }
                ]
            }
        }

        manager._apply_domain_removals(mock_client, changes)

        mock_client.domains.batch_delete_domains.assert_called_once()

    def test_apply_domain_changes(self):
        """Domain changes delete old and update."""
        manager = PiHoleManager("http://test", "password")
        mock_client = MagicMock()
        manager._client = mock_client

        changes = {
            "change": {
                "local": [
                    {
                        "domain": "blocked.example.com",
                        "type": "deny",
                        "kind": "exact",
                        "comment": "Updated",
                    }
                ],
                "remote": [
                    {
                        "domain": "blocked.example.com",
                        "type": "deny",
                        "kind": "exact",
                    }
                ],
            }
        }

        manager._apply_domain_changes(mock_client, changes)

        mock_client.domains.batch_delete_domains.assert_called_once()
        mock_client.domains.update_domain.assert_called_once()

    def test_update_domains_failure_returns_false(self):
        """API failure returns False."""
        manager = PiHoleManager("http://test", "password")
        mock_client = MagicMock()
        mock_client.domains.add_domain.side_effect = Exception("API Error")
        manager._client = mock_client

        changes = {
            "add": {
                "local": [
                    {
                        "domain": "blocked.example.com",
                        "type": "deny",
                        "kind": "exact",
                    }
                ]
            }
        }

        result = manager.update_domains(changes)

        assert result is False
