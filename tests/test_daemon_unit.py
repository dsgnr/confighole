"""Unit tests for daemon functionality."""

from __future__ import annotations

import os
from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
class TestDaemonEnvConfig:
    """Tests for daemon environment configuration."""

    def test_defaults_when_env_empty(self):
        """Default values when environment is empty."""
        from confighole.core.daemon import get_daemon_config_from_env

        env_vars = [
            "CONFIGHOLE_DAEMON_MODE",
            "CONFIGHOLE_DAEMON_INTERVAL",
            "CONFIGHOLE_CONFIG_PATH",
            "CONFIGHOLE_INSTANCE",
            "CONFIGHOLE_DRY_RUN",
        ]

        original = {var: os.environ.get(var) for var in env_vars}
        for var in env_vars:
            os.environ.pop(var, None)

        try:
            config = get_daemon_config_from_env()

            assert config["enabled"] is False
            assert config["interval"] == 300
            assert config["config_path"] is None
            assert config["instance"] is None
            assert config["dry_run"] is False
        finally:
            for var, value in original.items():
                if value is not None:
                    os.environ[var] = value

    def test_values_from_env(self):
        """Values are read from environment."""
        from confighole.core.daemon import get_daemon_config_from_env

        env_vars = {
            "CONFIGHOLE_DAEMON_MODE": "true",
            "CONFIGHOLE_DAEMON_INTERVAL": "600",
            "CONFIGHOLE_CONFIG_PATH": "/test/config.yaml",
            "CONFIGHOLE_INSTANCE": "test-instance",
            "CONFIGHOLE_DRY_RUN": "true",
        }

        original = {var: os.environ.get(var) for var in env_vars}
        os.environ.update(env_vars)

        try:
            config = get_daemon_config_from_env()

            assert config["enabled"] is True
            assert config["interval"] == 600
            assert config["config_path"] == "/test/config.yaml"
            assert config["instance"] == "test-instance"
            assert config["dry_run"] is True
        finally:
            for var, value in original.items():
                if value is not None:
                    os.environ[var] = value
                else:
                    os.environ.pop(var, None)

    def test_invalid_boolean_treated_as_false(self):
        """Invalid boolean values are treated as False."""
        from confighole.core.daemon import get_daemon_config_from_env

        os.environ["CONFIGHOLE_DAEMON_MODE"] = "invalid"
        os.environ["CONFIGHOLE_DRY_RUN"] = "maybe"

        try:
            config = get_daemon_config_from_env()

            assert config["enabled"] is False
            assert config["dry_run"] is False
        finally:
            os.environ.pop("CONFIGHOLE_DAEMON_MODE", None)
            os.environ.pop("CONFIGHOLE_DRY_RUN", None)

    def test_invalid_interval_raises(self):
        """Invalid interval raises ValueError."""
        from confighole.core.daemon import get_daemon_config_from_env

        os.environ["CONFIGHOLE_DAEMON_INTERVAL"] = "not_a_number"

        try:
            with pytest.raises(ValueError):
                get_daemon_config_from_env()
        finally:
            os.environ.pop("CONFIGHOLE_DAEMON_INTERVAL", None)


@pytest.mark.unit
class TestDaemonFromEnv:
    """Tests for running daemon from environment."""

    @patch("confighole.core.daemon.get_daemon_config_from_env")
    def test_disabled_exits(self, mock_get_config):
        """Disabled daemon exits with error."""
        from confighole.core.daemon import run_daemon_from_env

        mock_get_config.return_value = {"enabled": False}

        with pytest.raises(SystemExit) as exc_info:
            run_daemon_from_env()

        assert exc_info.value.code == 1

    @patch("confighole.core.daemon.get_daemon_config_from_env")
    def test_no_config_path_exits(self, mock_get_config):
        """Missing config path exits with error."""
        from confighole.core.daemon import run_daemon_from_env

        mock_get_config.return_value = {"enabled": True, "config_path": None}

        with pytest.raises(SystemExit) as exc_info:
            run_daemon_from_env()

        assert exc_info.value.code == 1

    @patch("confighole.core.daemon.ConfigHoleDaemon")
    @patch("confighole.core.daemon.get_daemon_config_from_env")
    def test_success_creates_and_runs_daemon(self, mock_get_config, mock_daemon_class):
        """Successful startup creates and runs daemon."""
        from confighole.core.daemon import run_daemon_from_env

        mock_get_config.return_value = {
            "enabled": True,
            "config_path": "/test/config.yaml",
            "interval": 300,
            "instance": None,
            "dry_run": False,
        }

        mock_daemon = Mock()
        mock_daemon_class.return_value = mock_daemon

        run_daemon_from_env()

        mock_daemon_class.assert_called_once_with(
            config_path="/test/config.yaml",
            interval=300,
            target_instance=None,
            dry_run=False,
        )
        mock_daemon.run.assert_called_once()


@pytest.mark.unit
class TestDaemonInitialisation:
    """Tests for daemon initialisation."""

    def test_attributes_set_correctly(self):
        """Daemon attributes are set correctly."""
        from confighole.core.daemon import ConfigHoleDaemon

        daemon = ConfigHoleDaemon(
            config_path="/test/config.yaml",
            interval=60,
            target_instance="test",
            dry_run=True,
        )

        assert daemon.config_path == "/test/config.yaml"
        assert daemon.interval == 60
        assert daemon.target_instance == "test"
        assert daemon.dry_run is True
        assert daemon.running is False

    def test_default_values(self):
        """Default values are applied."""
        from confighole.core.daemon import ConfigHoleDaemon

        daemon = ConfigHoleDaemon(config_path="/test/config.yaml")

        assert daemon.interval == 300
        assert daemon.target_instance is None
        assert daemon.dry_run is False


@pytest.mark.unit
class TestDaemonInstanceLoading:
    """Tests for daemon instance loading."""

    @patch("confighole.core.daemon.load_yaml_config")
    @patch("confighole.core.daemon.merge_global_settings")
    def test_loads_all_instances(self, mock_merge, mock_load):
        """All instances are loaded when no target."""
        from confighole.core.daemon import ConfigHoleDaemon

        mock_load.return_value = {"global": {}, "instances": []}
        mock_merge.return_value = [{"name": "a"}, {"name": "b"}]

        daemon = ConfigHoleDaemon(config_path="/test/config.yaml")
        instances = daemon._load_instances()

        assert len(instances) == 2

    @patch("confighole.core.daemon.load_yaml_config")
    @patch("confighole.core.daemon.merge_global_settings")
    def test_filters_by_target(self, mock_merge, mock_load):
        """Instances are filtered by target."""
        from confighole.core.daemon import ConfigHoleDaemon

        mock_load.return_value = {"global": {}, "instances": []}
        mock_merge.return_value = [{"name": "a"}, {"name": "b"}]

        daemon = ConfigHoleDaemon(
            config_path="/test/config.yaml",
            target_instance="a",
        )
        instances = daemon._load_instances()

        assert len(instances) == 1
        assert instances[0]["name"] == "a"

    @patch("confighole.core.daemon.load_yaml_config")
    @patch("confighole.core.daemon.merge_global_settings")
    def test_target_not_found_exits(self, mock_merge, mock_load):
        """Missing target instance exits."""
        from confighole.core.daemon import ConfigHoleDaemon

        mock_load.return_value = {"global": {}, "instances": []}
        mock_merge.return_value = [{"name": "a"}]

        daemon = ConfigHoleDaemon(
            config_path="/test/config.yaml",
            target_instance="missing",
        )

        with pytest.raises(SystemExit) as exc_info:
            daemon._load_instances()

        assert exc_info.value.code == 1


@pytest.mark.unit
class TestDaemonSync:
    """Tests for daemon sync operation."""

    @patch("confighole.core.daemon.process_instances")
    def test_sync_calls_process_instances(self, mock_process):
        """Sync calls process_instances correctly."""
        from confighole.core.daemon import ConfigHoleDaemon

        daemon = ConfigHoleDaemon(config_path="/test/config.yaml")
        daemon._load_instances = Mock(return_value=[{"name": "test"}])

        daemon._sync_instances()

        mock_process.assert_called_once_with([{"name": "test"}], "sync", dry_run=False)

    @patch("confighole.core.daemon.process_instances")
    def test_sync_with_dry_run(self, mock_process):
        """Sync passes dry_run flag."""
        from confighole.core.daemon import ConfigHoleDaemon

        daemon = ConfigHoleDaemon(config_path="/test/config.yaml", dry_run=True)
        daemon._load_instances = Mock(return_value=[{"name": "test"}])

        daemon._sync_instances()

        mock_process.assert_called_once_with([{"name": "test"}], "sync", dry_run=True)

    @patch("confighole.core.daemon.process_instances")
    def test_sync_handles_empty_instances(self, mock_process):
        """Sync handles empty instances gracefully."""
        from confighole.core.daemon import ConfigHoleDaemon

        daemon = ConfigHoleDaemon(config_path="/test/config.yaml")
        daemon._load_instances = Mock(return_value=[])

        daemon._sync_instances()

        mock_process.assert_not_called()


@pytest.mark.unit
class TestDaemonSignalHandling:
    """Tests for daemon signal handling."""

    def test_signal_handler_sets_running_false(self):
        """Signal handler sets running to False."""
        from confighole.core.daemon import ConfigHoleDaemon

        daemon = ConfigHoleDaemon(config_path="/test/config.yaml")
        daemon.running = True

        daemon._signal_handler(15, None)

        assert daemon.running is False
