"""Unit tests for CLI functionality."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


@pytest.mark.unit
class TestArgumentParser:
    """Tests for CLI argument parsing."""

    def test_help_message_content(self):
        """Help message contains expected content."""
        from confighole.cli import create_argument_parser

        parser = create_argument_parser()
        help_text = parser.format_help()

        assert "ConfigHole - The Pi-hole configuration manager" in help_text
        assert "--dump" in help_text
        assert "--diff" in help_text
        assert "--sync" in help_text
        assert "--daemon" in help_text
        assert "--dry-run" in help_text

    def test_operations_mutually_exclusive(self):
        """Operations are mutually exclusive."""
        from confighole.cli import create_argument_parser

        parser = create_argument_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["-c", "test.yaml", "--dump", "--diff"])

    def test_config_required(self):
        """Config file is required."""
        from confighole.cli import create_argument_parser

        parser = create_argument_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["--dump"])

    def test_operation_required(self):
        """At least one operation is required."""
        from confighole.cli import create_argument_parser

        parser = create_argument_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["-c", "test.yaml"])


@pytest.mark.unit
class TestCLIMain:
    """Tests for CLI main function."""

    @patch("confighole.cli.load_yaml_config")
    @patch("confighole.cli.merge_global_settings")
    @patch("confighole.cli.process_instances")
    def test_dump_operation(self, mock_process, mock_merge, mock_load):
        """Dump operation calls process_instances correctly."""
        from confighole.cli import main

        mock_load.return_value = {"global": {}, "instances": []}
        mock_merge.return_value = [{"name": "test"}]
        mock_process.return_value = [{"name": "test", "config": {}}]

        with patch("sys.argv", ["confighole", "-c", "test.yaml", "--dump"]):
            try:
                main()
            except SystemExit:
                pass

        mock_process.assert_called_once_with([{"name": "test"}], "dump", dry_run=False)

    @patch("confighole.cli.load_yaml_config")
    def test_no_instances_exits(self, mock_load):
        """No instances in config causes exit."""
        from confighole.cli import main

        mock_load.return_value = {"global": {}, "instances": []}

        with patch("sys.argv", ["confighole", "-c", "test.yaml", "--dump"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

    @patch("confighole.cli.load_yaml_config")
    @patch("confighole.cli.merge_global_settings")
    def test_instance_filter_not_found_exits(self, mock_merge, mock_load):
        """Instance filter with no match causes exit."""
        from confighole.cli import main

        mock_load.return_value = {"global": {}, "instances": []}
        mock_merge.return_value = [{"name": "other"}]

        with patch(
            "sys.argv", ["confighole", "-c", "test.yaml", "-i", "missing", "--dump"]
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

    @patch("confighole.cli.get_global_daemon_settings")
    @patch("confighole.cli.load_yaml_config")
    def test_global_verbosity_used(self, mock_load, mock_daemon_settings):
        """Global verbosity is used when CLI doesn't specify."""
        from confighole.cli import main

        mock_load.return_value = {"global": {"verbosity": 2}, "instances": []}
        mock_daemon_settings.return_value = {
            "daemon_mode": False,
            "daemon_interval": 300,
            "verbosity": 2,
            "dry_run": False,
        }

        with patch("sys.argv", ["confighole", "-c", "test.yaml", "--dump"]):
            with patch("confighole.cli.setup_logging") as mock_logging:
                try:
                    main()
                except SystemExit:
                    pass

        mock_logging.assert_called_with(2)

    @patch("confighole.cli.load_yaml_config")
    @patch("confighole.cli.merge_global_settings")
    @patch("confighole.cli.process_instances")
    def test_no_results_logs_message(self, mock_process, mock_merge, mock_load):
        """No results logs appropriate message."""
        from confighole.cli import main

        mock_load.return_value = {"global": {}, "instances": []}
        mock_merge.return_value = [{"name": "test"}]
        mock_process.return_value = []

        with patch("sys.argv", ["confighole", "-c", "test.yaml", "--dump"]):
            with patch("logging.info") as mock_log:
                try:
                    main()
                except SystemExit:
                    pass

        mock_log.assert_called_with("No results to display")


@pytest.mark.unit
class TestDaemonModeDetection:
    """Tests for daemon mode environment detection."""

    @patch.dict(os.environ, {"CONFIGHOLE_DAEMON_MODE": "true"})
    @patch("confighole.cli.run_daemon_from_env")
    def test_env_daemon_mode_detected(self, mock_run_daemon):
        """Daemon mode from environment is detected."""
        from confighole.cli import main

        mock_run_daemon.side_effect = SystemExit(0)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        mock_run_daemon.assert_called_once()


@pytest.mark.unit
class TestLoggingSetup:
    """Tests for logging configuration."""

    def test_setup_logging_callable(self):
        """setup_logging is callable at all verbosity levels."""
        from confighole.cli import setup_logging

        setup_logging(0)
        setup_logging(1)
        setup_logging(2)
        setup_logging(10)  # Beyond max level


@pytest.mark.unit
class TestArgumentValidation:
    """Tests for argument validation."""

    @patch("confighole.cli.load_yaml_config")
    @patch("confighole.cli.merge_global_settings")
    def test_dry_run_requires_sync_or_daemon(self, mock_merge, mock_load):
        """--dry-run requires --sync or --daemon."""
        from confighole.cli import main

        mock_load.return_value = {"global": {}, "instances": []}
        mock_merge.return_value = [{"name": "test"}]

        with patch(
            "sys.argv", ["confighole", "-c", "test.yaml", "--dump", "--dry-run"]
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

    @patch("confighole.cli.load_yaml_config")
    @patch("confighole.cli.merge_global_settings")
    def test_interval_requires_daemon(self, mock_merge, mock_load):
        """--interval requires --daemon."""
        from confighole.cli import main

        mock_load.return_value = {"global": {}, "instances": []}
        mock_merge.return_value = [{"name": "test"}]

        with patch(
            "sys.argv", ["confighole", "-c", "test.yaml", "--dump", "--interval", "60"]
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1


@pytest.mark.unit
class TestOperationMode:
    """Tests for operation mode detection."""

    def test_get_operation_mode_dump(self):
        """Dump operation is detected."""
        from argparse import Namespace

        from confighole.cli import get_operation_mode

        args = Namespace(dump=True, diff=False, daemon=False, sync=False)
        assert get_operation_mode(args) == "dump"

    def test_get_operation_mode_diff(self):
        """Diff operation is detected."""
        from argparse import Namespace

        from confighole.cli import get_operation_mode

        args = Namespace(dump=False, diff=True, daemon=False, sync=False)
        assert get_operation_mode(args) == "diff"

    def test_get_operation_mode_daemon(self):
        """Daemon operation is detected."""
        from argparse import Namespace

        from confighole.cli import get_operation_mode

        args = Namespace(dump=False, diff=False, daemon=True, sync=False)
        assert get_operation_mode(args) == "daemon"

    def test_get_operation_mode_sync_default(self):
        """Sync is default when no other operation."""
        from argparse import Namespace

        from confighole.cli import get_operation_mode

        args = Namespace(dump=False, diff=False, daemon=False, sync=True)
        assert get_operation_mode(args) == "sync"


@pytest.mark.unit
class TestInstanceFiltering:
    """Tests for instance filtering."""

    def test_filter_no_target_returns_all(self):
        """No target returns all instances."""
        from confighole.cli import filter_instances

        instances = [{"name": "a"}, {"name": "b"}]
        assert filter_instances(instances, None) == instances

    def test_filter_with_target_returns_match(self):
        """Target returns matching instance."""
        from confighole.cli import filter_instances

        instances = [{"name": "a"}, {"name": "b"}]
        result = filter_instances(instances, "a")

        assert len(result) == 1
        assert result[0]["name"] == "a"

    def test_filter_no_match_exits(self):
        """No match causes exit."""
        from confighole.cli import filter_instances

        instances = [{"name": "a"}]

        with pytest.raises(SystemExit) as exc_info:
            filter_instances(instances, "missing")

        assert exc_info.value.code == 1


@pytest.mark.unit
class TestSettingsResolution:
    """Tests for settings resolution."""

    def test_cli_verbosity_takes_precedence(self):
        """CLI verbosity overrides global."""
        from argparse import Namespace

        from confighole.cli import resolve_settings

        args = Namespace(verbose=2, interval=300, dry_run=False, daemon=False)
        global_settings = {"verbosity": 1}

        result = resolve_settings(args, global_settings)

        assert result["verbosity"] == 2

    def test_global_verbosity_used_when_cli_zero(self):
        """Global verbosity used when CLI is 0."""
        from argparse import Namespace

        from confighole.cli import resolve_settings

        args = Namespace(verbose=0, interval=300, dry_run=False, daemon=False)
        global_settings = {"verbosity": 2}

        result = resolve_settings(args, global_settings)

        assert result["verbosity"] == 2

    def test_dry_run_from_cli_or_global(self):
        """dry_run from CLI or global."""
        from argparse import Namespace

        from confighole.cli import resolve_settings

        args = Namespace(verbose=0, interval=300, dry_run=True, daemon=False)
        result = resolve_settings(args, {})
        assert result["dry_run"] is True

        args = Namespace(verbose=0, interval=300, dry_run=False, daemon=False)
        result = resolve_settings(args, {"dry_run": True})
        assert result["dry_run"] is True
