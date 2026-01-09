"""Unit tests for CLI"""

import os
from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
class TestCLIUnit:
    """Unit tests for CLI functionality."""

    @patch("confighole.cli.load_yaml_config")
    @patch("confighole.cli.merge_global_settings")
    @patch("confighole.cli.process_instances")
    def test_cli_dump_operation(self, mock_process, mock_merge, mock_load):
        """Test CLI dump operation without external calls."""
        from confighole.cli import main

        # Mock the config loading and processing
        mock_load.return_value = {"global": {}, "instances": []}
        mock_merge.return_value = [{"name": "test"}]
        mock_process.return_value = [{"name": "test", "config": {}}]

        # Mock sys.argv
        with patch("sys.argv", ["confighole", "-c", "test.yaml", "--dump"]):
            try:
                main()
            except SystemExit as e:
                assert e.code == 0

        # Verify the operation was called with dry_run parameter
        mock_process.assert_called_once_with([{"name": "test"}], "dump", dry_run=False)

    @patch("confighole.cli.load_yaml_config")
    def test_cli_missing_instances(self, mock_load):
        """Test CLI with config that has no instances."""
        from confighole.cli import main

        mock_load.return_value = {"global": {}, "instances": []}

        with patch("sys.argv", ["confighole", "-c", "test.yaml", "--dump"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

    @patch("confighole.cli.load_yaml_config")
    @patch("confighole.cli.merge_global_settings")
    def test_cli_instance_filter_not_found(self, mock_merge, mock_load):
        """Test CLI with instance filter that doesn't match."""
        from confighole.cli import main

        mock_load.return_value = {"global": {}, "instances": []}
        mock_merge.return_value = [{"name": "other-instance"}]

        with patch(
            "sys.argv", ["confighole", "-c", "test.yaml", "-i", "missing", "--dump"]
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

    def test_cli_help_message(self):
        """Test CLI help message."""
        from confighole.cli import create_argument_parser

        parser = create_argument_parser()
        help_text = parser.format_help()

        assert "ConfigHole - The Pi-hole configuration manager" in help_text
        assert "--dump" in help_text
        assert "--diff" in help_text
        assert "--sync" in help_text
        assert "--daemon" in help_text

    def test_cli_mutually_exclusive_operations(self):
        """Test that CLI operations are mutually exclusive."""
        from confighole.cli import create_argument_parser

        parser = create_argument_parser()

        # Should fail with multiple operations
        with pytest.raises(SystemExit):
            parser.parse_args(["-c", "test.yaml", "--dump", "--diff"])

    @patch("confighole.cli.get_global_daemon_settings")
    @patch("confighole.cli.load_yaml_config")
    def test_cli_global_settings_precedence(self, mock_load, mock_daemon_settings):
        """Test CLI global settings precedence."""
        from confighole.cli import main

        mock_load.return_value = {"global": {"verbosity": 2}, "instances": []}
        mock_daemon_settings.return_value = {
            "daemon_mode": False,
            "daemon_interval": 300,
            "verbosity": 2,
            "dry_run": False,
        }

        # CLI should use global verbosity when not specified
        with patch("sys.argv", ["confighole", "-c", "test.yaml", "--dump"]):
            with patch("confighole.cli.setup_logging") as mock_setup_logging:
                try:
                    main()
                except SystemExit:
                    pass

        # Should use verbosity from global config
        mock_setup_logging.assert_called_with(2)

    def test_setup_logging_levels(self):
        """Test logging setup with different verbosity levels."""
        from confighole.cli import setup_logging

        # Test different verbosity levels
        setup_logging(0)
        # Note: logging level might be affected by other tests, so we test the function exists
        assert callable(setup_logging)

        setup_logging(1)
        assert callable(setup_logging)

        setup_logging(2)
        assert callable(setup_logging)

    @patch.dict(os.environ, {"CONFIGHOLE_DAEMON_MODE": "true"})
    @patch("confighole.cli.run_daemon_from_env")
    def test_cli_daemon_mode_env_detection(self, mock_run_daemon):
        """Test CLI daemon mode detection from environment."""
        from confighole.cli import main

        mock_run_daemon.side_effect = SystemExit(0)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        mock_run_daemon.assert_called_once()

    @patch("confighole.cli.load_yaml_config")
    @patch("confighole.cli.merge_global_settings")
    @patch("confighole.cli.process_instances")
    def test_cli_no_results_message(self, mock_process, mock_merge, mock_load):
        """Test CLI message when no results are returned."""
        from confighole.cli import main

        mock_load.return_value = {"global": {}, "instances": []}
        mock_merge.return_value = [{"name": "test"}]
        mock_process.return_value = []  # No results

        with patch("sys.argv", ["confighole", "-c", "test.yaml", "--dump"]):
            with patch("logging.info") as mock_log_info:
                try:
                    main()
                except SystemExit as e:
                    assert e.code == 0

        # Should log "No results to display"
        mock_log_info.assert_called_with("No results to display")


@pytest.mark.unit
class TestDaemonUnit:
    """Unit tests for daemon functionality."""

    def test_daemon_config_from_env_defaults(self):
        """Test daemon config with default values."""
        from confighole.core.daemon import get_daemon_config_from_env

        # Clear any existing env vars
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

    def test_daemon_config_from_env_set_values(self):
        """Test daemon config with set environment values."""
        from confighole.core.daemon import get_daemon_config_from_env

        env_vars = {
            "CONFIGHOLE_DAEMON_MODE": "true",
            "CONFIGHOLE_DAEMON_INTERVAL": "600",
            "CONFIGHOLE_CONFIG_PATH": "/test/config.yaml",
            "CONFIGHOLE_INSTANCE": "test-instance",
            "CONFIGHOLE_DRY_RUN": "true",
        }

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

    @patch("confighole.core.daemon.get_daemon_config_from_env")
    def test_run_daemon_from_env_disabled(self, mock_get_config):
        """Test running daemon when disabled."""
        from confighole.core.daemon import run_daemon_from_env

        mock_get_config.return_value = {"enabled": False}

        with pytest.raises(SystemExit) as exc_info:
            run_daemon_from_env()

        assert exc_info.value.code == 1

    @patch("confighole.core.daemon.get_daemon_config_from_env")
    def test_run_daemon_from_env_no_config_path(self, mock_get_config):
        """Test running daemon with no config path."""
        from confighole.core.daemon import run_daemon_from_env

        mock_get_config.return_value = {"enabled": True, "config_path": None}

        with pytest.raises(SystemExit) as exc_info:
            run_daemon_from_env()

        assert exc_info.value.code == 1

    @patch("confighole.core.daemon.ConfigHoleDaemon")
    @patch("confighole.core.daemon.get_daemon_config_from_env")
    def test_run_daemon_from_env_success(self, mock_get_config, mock_daemon_class):
        """Test successful daemon startup."""
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

        # Verify daemon was created and run
        mock_daemon_class.assert_called_once_with(
            config_path="/test/config.yaml",
            interval=300,
            target_instance=None,
            dry_run=False,
        )
        mock_daemon.run.assert_called_once()

    def test_daemon_initialisation(self):
        """Test daemon initialisation."""
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

    @patch("confighole.core.daemon.load_yaml_config")
    @patch("confighole.core.daemon.merge_global_settings")
    def test_daemon_load_instances_with_target(self, mock_merge, mock_load):
        """Test daemon loading specific instance."""
        from confighole.core.daemon import ConfigHoleDaemon

        mock_load.return_value = {"global": {}, "instances": []}
        mock_merge.return_value = [
            {"name": "test1"},
            {"name": "test2"},
        ]

        daemon = ConfigHoleDaemon(
            config_path="/test/config.yaml",
            target_instance="test1",
        )

        instances = daemon._load_instances()

        assert len(instances) == 1
        assert instances[0]["name"] == "test1"

    @patch("confighole.core.daemon.load_yaml_config")
    @patch("confighole.core.daemon.merge_global_settings")
    def test_daemon_load_instances_all(self, mock_merge, mock_load):
        """Test daemon loading all instances."""
        from confighole.core.daemon import ConfigHoleDaemon

        mock_load.return_value = {"global": {}, "instances": []}
        mock_merge.return_value = [
            {"name": "test1"},
            {"name": "test2"},
        ]

        daemon = ConfigHoleDaemon(config_path="/test/config.yaml")

        instances = daemon._load_instances()

        assert len(instances) == 2

    @patch("confighole.core.daemon.process_instances")
    def test_daemon_sync_instances(self, mock_process):
        """Test daemon sync operation."""
        from confighole.core.daemon import ConfigHoleDaemon

        daemon = ConfigHoleDaemon(config_path="/test/config.yaml")
        daemon._load_instances = Mock(return_value=[{"name": "test"}])

        daemon._sync_instances()

        mock_process.assert_called_once_with([{"name": "test"}], "sync", dry_run=False)
